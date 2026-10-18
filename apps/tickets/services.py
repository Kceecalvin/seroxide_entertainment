"""Order creation, stock control, and ticket fulfilment (QR generation).

Stock model: `TicketType.quantity_sold` is reserved at order **creation**
(inside the same locked transaction that validates availability), not at
payment success. This closes the overselling window where many buyers could
all pass the "is there stock?" check against the same last-few tickets while
their payments were still pending. Reserved-but-unpaid stock is released via
`release_order_stock()`, called on a failed/cancelled payment or by the
`expire_stale_orders` management command for orders abandoned mid-checkout.
"""
import io

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.events.models import Event

from .emails import send_order_confirmation_email, send_waitlist_spot_available_email
from .models import Order, OrderItem, OrderStatus, Ticket, TicketStatus, TicketType, WaitlistEntry


class OrderError(Exception):
    """Raised when an order can't be fulfilled (sold out, closed sales, bad quantity)."""


@transaction.atomic
def admit_ticket(ticket, user, checked_in_at):
    """Serialize admission with refunds and recheck status on the UPDATE itself.

    A joined UPDATE can put the validity predicate inside an ID subquery;
    PostgreSQL may then reuse that snapshot after waiting on a concurrent scan.
    Keep the ticket-status predicate on the outer UPDATE and lock the order in
    the same order as refund/fulfillment operations.
    """
    order = Order.objects.select_for_update().get(pk=ticket.order_item.order_id)
    if order.status != OrderStatus.PAID:
        return 0
    return Ticket.objects.filter(pk=ticket.pk, status=TicketStatus.VALID).update(
        status=TicketStatus.USED, checked_in_at=checked_in_at, checked_in_by=user)


@transaction.atomic
def create_order(*, event: Event, buyer_name: str, buyer_email: str, buyer_phone: str, cart: dict, buyer=None):
    """cart: {ticket_type_id (str/int): quantity (int)}"""
    event = Event.objects.select_for_update().get(pk=event.pk)
    if not event.is_published:
        raise OrderError('This event is not on sale.')
    if event.is_past:
        raise OrderError('This event has already taken place.')

    order = Order.objects.create(
        event=event, buyer_name=buyer_name, buyer_email=buyer_email, buyer_phone=buyer_phone,
        buyer=buyer if buyer and buyer.is_authenticated else None,
        commission_rate=settings.PLATFORM_COMMISSION_RATE,
    )

    total_items = 0
    for type_id, qty in cart.items():
        qty = int(qty)
        if qty <= 0:
            continue
        try:
            ticket_type = TicketType.objects.select_for_update().get(pk=type_id, event=event, is_active=True)
        except (TicketType.DoesNotExist, ValueError, TypeError):
            raise OrderError('Choose an available ticket type for this event.')
        if ticket_type.sales_end and ticket_type.sales_end < timezone.now():
            raise OrderError(f'Sales for "{ticket_type.name}" tickets have closed.')
        if qty > ticket_type.max_per_order:
            raise OrderError(f'You can buy at most {ticket_type.max_per_order} "{ticket_type.name}" tickets per order.')
        if qty > ticket_type.remaining:
            raise OrderError(f'Only {ticket_type.remaining} "{ticket_type.name}" tickets remain.')

        # Reserve the stock now, while still holding the row lock — this is
        # the actual fix for oversold tickets: nobody else's concurrent
        # create_order() can see this stock as "remaining" once we commit.
        ticket_type.quantity_sold += qty
        ticket_type.save(update_fields=['quantity_sold'])

        OrderItem.objects.create(order=order, ticket_type=ticket_type, quantity=qty, unit_price=ticket_type.price)
        total_items += qty

    if total_items == 0:
        raise OrderError('Select at least one ticket.')

    order.recalculate_total()
    return order


@transaction.atomic
def release_order_stock(order: Order, *, new_status: str):
    """Give reserved-but-unpaid stock back to the pool. Call this — and only
    this — for orders that will never be paid (failed payment, expired
    checkout). Never call it on a PAID order."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != OrderStatus.PENDING:
        return order  # already resolved (paid/cancelled/expired) — nothing to release

    for item in order.items.select_related('ticket_type').select_for_update():
        ticket_type = TicketType.objects.select_for_update().get(pk=item.ticket_type_id)
        ticket_type.quantity_sold = max(0, ticket_type.quantity_sold - item.quantity)
        ticket_type.save(update_fields=['quantity_sold'])
        notify_waitlist(ticket_type)

    order.status = new_status
    order.save(update_fields=['status'])
    return order


@transaction.atomic
def notify_waitlist(ticket_type: TicketType):
    """Call whenever quantity_sold drops (a refund, or a pending order being
    cancelled/expired) — email the oldest un-notified waitlist entries, up to
    however many spots just freed up. First come, first served on actually
    completing checkout, same as any real sale.

    notified_at is set before the email is sent (mirroring
    send_order_confirmation_email's best-effort pattern) so a slow or failed
    send can't cause the same person to be re-notified on the next stock
    change — not select_for_update()'d, since a rare double-notify from a
    tight race is a UX rough edge, not a correctness bug like overselling.
    """
    remaining = ticket_type.remaining
    if remaining <= 0:
        return
    entries = list(
        WaitlistEntry.objects.select_for_update().filter(ticket_type=ticket_type, notified_at__isnull=True)[:remaining]
    )
    if not entries:
        return
    WaitlistEntry.objects.filter(pk__in=[e.pk for e in entries]).update(notified_at=timezone.now())
    for entry in entries:
        send_waitlist_spot_available_email(entry)


def _build_verify_url(serial):
    scheme = 'http' if settings.DEBUG else 'https'
    return f'{scheme}://{settings.SITE_DOMAIN}/tickets/verify/{serial}/'


def _generate_qr_file(data: str) -> ContentFile:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return ContentFile(buf.getvalue())


@transaction.atomic
def fulfill_order(order: Order):
    """Mark an order paid and mint tickets with QR codes. Stock was already
    reserved in create_order(), so this never touches quantity_sold — it
    only ever mints tickets, and it's safe to call twice for the same order
    (e.g. a duplicated payment-provider callback)."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == OrderStatus.PAID:
        return order  # already fulfilled — idempotent, and now race-safe:
        # the lock above means a concurrent second call blocks until this
        # transaction commits, then sees PAID and returns here instead of
        # minting a second set of tickets.

    if order.status != OrderStatus.PENDING:
        # The reservation was already released. A late payment must acquire
        # fresh stock under lock, or remain in reconciliation without tickets.
        for item in order.items.order_by('ticket_type_id'):
            tier = TicketType.objects.select_for_update().get(pk=item.ticket_type_id)
            if tier.remaining < item.quantity:
                raise OrderError('Late payment has no available stock; manual reconciliation required.')
            tier.quantity_sold += item.quantity
            tier.save(update_fields=['quantity_sold'])

    for item in order.items.select_related('ticket_type'):
        for _ in range(item.quantity):
            ticket = Ticket.objects.create(order_item=item)
            qr_file = _generate_qr_file(_build_verify_url(ticket.serial))
            ticket.qr_code.save(f'{ticket.serial}.png', qr_file, save=True)

    order.status = OrderStatus.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=['status', 'paid_at'])

    # Send after commit — email I/O has no place inside the DB transaction,
    # and a slow/broken send must never roll back a paid order.
    send_order_confirmation_email(order)
    return order
