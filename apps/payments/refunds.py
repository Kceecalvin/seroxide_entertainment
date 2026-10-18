"""Refund issuance for completed payments.

Stripe has a real refund API, called directly here (same `requests`-based
style as stripe_client.py, for the same auditability reason). M-Pesa/Daraja
has no equivalent simple merchant-refund endpoint — sending money back
requires the separate B2C API product, which this project doesn't have
credentials for. So an M-Pesa refund here means: a staff member has already
sent the money back manually through Safaricom's own tools (the business
portal or *234# reversal), and enters the resulting Safaricom transaction
code as the audit record.

Either way, issuing a refund cancels the order, voids its tickets (so they
stop scanning as valid at the door), and releases the stock back to the pool.
"""
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.tickets.models import Order, OrderStatus, Ticket, TicketStatus, TicketType
from apps.tickets.services import notify_waitlist

from .models import Payment, PaymentMethod, PaymentStatus
from .paystack_client import PaystackError, refund_transaction
from .stripe_client import API_BASE_URL


class RefundError(Exception):
    """Raised when a refund can't be issued."""


def _refund_via_stripe(payment):
    if not payment.stripe_payment_intent_id:
        raise RefundError('This Stripe payment has no payment_intent_id on record — cannot refund automatically.')
    try:
        resp = requests.post(
            f'{API_BASE_URL}/refunds',
            data={'payment_intent': payment.stripe_payment_intent_id},
            auth=(settings.STRIPE_SECRET_KEY, ''),
            timeout=15,
        )
    except requests.RequestException as exc:
        raise RefundError(f'Could not reach Stripe: {exc}') from exc
    body = resp.json()
    if resp.status_code >= 400:
        raise RefundError(body.get('error', {}).get('message') or str(body))
    return body['id']


def _refund_via_paystack(payment):
    if not payment.paystack_reference:
        raise RefundError('This Paystack payment has no reference on record — cannot refund automatically.')
    try:
        return refund_transaction(payment.paystack_reference)
    except PaystackError as exc:
        raise RefundError(f'Could not reach Paystack: {exc}') from exc


@transaction.atomic
def issue_refund(payment: Payment, *, manual_reference: str = ''):
    """manual_reference is required for M-Pesa (the Safaricom transaction
    code proving the money was already sent back) and ignored for Stripe/Paystack
    (the real refund id from their API is used instead)."""
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == PaymentStatus.REFUNDED:
        return payment  # idempotent — already done
    if payment.status != PaymentStatus.COMPLETED:
        raise RefundError(f'Only a completed payment can be refunded (this one is "{payment.get_status_display()}").')

    if settings.DEBUG and getattr(settings, 'REFUNDS_SIMULATE', False):
        refund_ref = f'SIM-REFUND-{payment.pk}'
    elif payment.method == PaymentMethod.STRIPE:
        refund_ref = _refund_via_stripe(payment)
    elif payment.method == PaymentMethod.PAYSTACK:
        refund_ref = _refund_via_paystack(payment)
    else:
        manual_reference = manual_reference.strip()
        if not manual_reference:
            raise RefundError(
                'M-Pesa has no automatic refund API — send the money back manually via '
                "Safaricom's business portal first, then enter the resulting transaction code here."
            )
        refund_ref = manual_reference

    payment.status = PaymentStatus.REFUNDED
    payment.refunded_at = timezone.now()
    payment.refund_reference = refund_ref
    payment.save(update_fields=['status', 'refunded_at', 'refund_reference'])

    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if order.status == OrderStatus.PAID:
        for item in order.items.select_related('ticket_type').select_for_update():
            ticket_type = TicketType.objects.select_for_update().get(pk=item.ticket_type_id)
            ticket_type.quantity_sold = max(0, ticket_type.quantity_sold - item.quantity)
            ticket_type.save(update_fields=['quantity_sold'])
            notify_waitlist(ticket_type)
        Ticket.objects.filter(order_item__order=order).update(status=TicketStatus.CANCELLED)
        order.status = OrderStatus.CANCELLED
        order.save(update_fields=['status'])

    if order.buyer_email:
        from apps.core.mailer import notify
        from django.urls import reverse
        notify(order.buyer_email, 'Your booking has been cancelled',
               f'Order {order.reference} for {order.event.title} is cancelled and its tickets are no longer valid. '
               f'Refund reference: {refund_ref}. Card refund processing depends on your provider; this message is not a bank settlement confirmation.',
               reverse('tickets:my_tickets'))
    return payment
