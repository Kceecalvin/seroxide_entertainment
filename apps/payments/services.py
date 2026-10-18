"""Order-to-payment orchestration: kick off payments (M-Pesa STK / Paystack
Checkout — Stripe functions remain for existing
Payment rows only, see PaymentMethod.STRIPE) and process the results each
provider reports back."""
import logging
from decimal import Decimal
from django.db import transaction

from django.conf import settings
from django.utils.crypto import get_random_string

from apps.tickets.models import Order, OrderStatus
from apps.tickets.services import fulfill_order, release_order_stock

from .mpesa import MpesaClient, MpesaError
from .models import Payment, PaymentMethod, PaymentStatus
from .paystack_client import PaystackError, initialize_transaction, verify_transaction
from .stripe_client import StripeError, create_checkout_session

logger = logging.getLogger(__name__)


def initiate_payment(order: Order, *, phone_number: str) -> Payment:
    payment = Payment.objects.create(
        order=order, method=PaymentMethod.MPESA, phone_number=phone_number, amount=order.total_amount
    )

    if settings.MPESA_SIMULATE:
        # No live Daraja credentials configured — simulate an instant successful payment
        # so the full booking flow (order -> pay -> ticket issued) can be exercised locally.
        payment.status = PaymentStatus.COMPLETED
        payment.mpesa_receipt_number = f'SIM{get_random_string(8, allowed_chars="0123456789ABCDEFGHJKLMNPQRSTUVWXYZ")}'
        payment.result_code = '0'
        payment.result_desc = 'Simulated payment (MPESA_SIMULATE=1, no live credentials configured)'
        payment.save()
        fulfill_order(order)
        return payment

    try:
        response = MpesaClient().stk_push(
            phone_number=phone_number,
            amount=order.total_amount,
            account_reference=order.reference,
            transaction_desc=f'{settings.SITE_NAME} tickets — {order.event.title}',
        )
    except MpesaError as exc:
        logger.warning('STK push failed for order %s: %s', order.reference, exc)
        payment.status = PaymentStatus.FAILED
        payment.result_desc = str(exc)[:255]
        payment.save()
        release_order_stock(order, new_status=OrderStatus.CANCELLED)
        return payment

    payment.checkout_request_id = response.get('CheckoutRequestID', '')
    payment.merchant_request_id = response.get('MerchantRequestID', '')
    payment.save()
    return payment


def initiate_stripe_payment(order: Order, *, success_url: str, cancel_url: str) -> tuple[Payment, str | None]:
    """Returns (payment, redirect_url). redirect_url is None if the attempt
    failed outright (caller should show an error, not redirect)."""
    payment = Payment.objects.create(order=order, method=PaymentMethod.STRIPE, amount=order.total_amount)

    if settings.STRIPE_SIMULATE:
        # Mirrors MPESA_SIMULATE — instant "paid" for local/dev exercising of the
        # full flow with no live Stripe keys configured.
        payment.status = PaymentStatus.COMPLETED
        payment.stripe_payment_intent_id = f'SIM_PI_{get_random_string(14)}'
        payment.result_desc = 'Simulated payment (STRIPE_SIMULATE=1, no live keys configured)'
        payment.save()
        fulfill_order(order)
        return payment, success_url

    try:
        session = create_checkout_session(order=order, success_url=success_url, cancel_url=cancel_url)
    except StripeError as exc:
        logger.warning('Stripe Checkout Session creation failed for order %s: %s', order.reference, exc)
        payment.status = PaymentStatus.FAILED
        payment.result_desc = str(exc)[:255]
        payment.save()
        release_order_stock(order, new_status=OrderStatus.CANCELLED)
        return payment, None

    payment.stripe_session_id = session.get('id', '')
    payment.save()
    return payment, session.get('url')


def initiate_paystack_payment(order: Order, *, callback_url: str) -> tuple[Payment, str | None]:
    """Returns (payment, redirect_url). redirect_url is None if the attempt
    failed outright (caller should show an error, not redirect)."""
    payment = Payment.objects.create(order=order, method=PaymentMethod.PAYSTACK, amount=order.total_amount)
    # Set once the row (and its pk) exists — Paystack requires this unique per
    # transaction attempt, so bare order.reference isn't safe to reuse if a
    # second attempt happens (e.g. the first failed and the buyer retries).
    reference = f'{order.reference}-P{payment.pk}'
    payment.paystack_reference = reference
    payment.save(update_fields=['paystack_reference'])

    if settings.PAYSTACK_SIMULATE:
        # Mirrors MPESA_SIMULATE/STRIPE_SIMULATE — instant "paid" for local/dev
        # exercising of the full flow with no live Paystack keys configured.
        payment.status = PaymentStatus.COMPLETED
        payment.result_desc = 'Simulated payment (PAYSTACK_SIMULATE=1, no live keys configured)'
        payment.save()
        fulfill_order(order)
        return payment, callback_url

    try:
        data = initialize_transaction(order=order, reference=reference, callback_url=callback_url)
    except PaystackError as exc:
        logger.warning('Paystack Initialize Transaction failed for order %s: %s', order.reference, exc)
        payment.status = PaymentStatus.FAILED
        payment.result_desc = str(exc)[:255]
        payment.save()
        release_order_stock(order, new_status=OrderStatus.CANCELLED)
        return payment, None

    return payment, data.get('authorization_url')


@transaction.atomic
def handle_stk_callback(payload: dict) -> Payment | None:
    """Process Safaricom's asynchronous STK callback payload."""
    stk_callback = payload.get('Body', {}).get('stkCallback', {})
    checkout_request_id = stk_callback.get('CheckoutRequestID')
    if not checkout_request_id:
        logger.warning('M-Pesa callback missing CheckoutRequestID: %s', payload)
        return None

    try:
        payment = Payment.objects.select_for_update().select_related('order').get(checkout_request_id=checkout_request_id)
    except Payment.DoesNotExist:
        logger.warning('M-Pesa callback for unknown CheckoutRequestID: %s', checkout_request_id)
        return None

    if payment.status in (PaymentStatus.COMPLETED, PaymentStatus.REFUNDED):
        return payment  # already processed — ignore any duplicate/replayed callback

    payment.raw_callback = payload
    payment.result_code = str(stk_callback.get('ResultCode', ''))
    payment.result_desc = stk_callback.get('ResultDesc', '')[:255]

    if str(stk_callback.get('ResultCode')) == '0':
        items = {
            item['Name']: item.get('Value')
            for item in stk_callback.get('CallbackMetadata', {}).get('Item', [])
        }

        # Never trust the callback's success flag alone — confirm the amount Safaricom
        # says was paid actually matches what this order was charged before minting tickets.
        try:
            paid_amount = round(float(items.get('Amount')))
            expected_amount = round(float(payment.amount))
        except (TypeError, ValueError):
            paid_amount = None
            expected_amount = round(float(payment.amount))

        if paid_amount != expected_amount:
            logger.error(
                'M-Pesa callback amount mismatch for %s: expected %s, got %s',
                checkout_request_id, expected_amount, paid_amount,
            )
            payment.status = PaymentStatus.FAILED
            payment.result_desc = 'Amount mismatch — payment not trusted'
            payment.save()
            release_order_stock(payment.order, new_status=OrderStatus.CANCELLED)
            return payment

        payment.mpesa_receipt_number = items.get('MpesaReceiptNumber', '')
        payment.status = PaymentStatus.COMPLETED
        payment.save()
        if payment.order.status != OrderStatus.PAID:
            try:
                fulfill_order(payment.order)
            except Exception:
                # Money is already confirmed received (payment.status is COMPLETED
                # above) — a failure here means a paid order with no ticket, the
                # exact case `find_orphaned_payments` exists to catch. Log loudly
                # so it's visible immediately, not just on the next reconciliation run.
                logger.exception(
                    'fulfill_order failed after payment was confirmed for order %s (payment %s) — '
                    'money received, no ticket minted. Needs manual reconciliation.',
                    payment.order.reference, payment.pk,
                )
    else:
        payment.status = PaymentStatus.FAILED
        payment.save()
        release_order_stock(payment.order, new_status=OrderStatus.CANCELLED)

    return payment


@transaction.atomic
def handle_stripe_event(event: dict) -> Payment | None:
    """Process a verified Stripe webhook event. Only checkout.session.completed
    (and its async-payment counterparts) triggers fulfilment; everything else
    is acknowledged and ignored."""
    event_type = event.get('type', '')
    if event_type not in ('checkout.session.completed', 'checkout.session.async_payment_succeeded',
                           'checkout.session.async_payment_failed'):
        return None

    session = event.get('data', {}).get('object', {})
    session_id = session.get('id')
    if not session_id:
        logger.warning('Stripe event %s missing session id: %s', event_type, event)
        return None

    try:
        payment = Payment.objects.select_for_update().select_related('order').get(stripe_session_id=session_id)
    except Payment.DoesNotExist:
        logger.warning('Stripe event for unknown session id: %s', session_id)
        return None

    if payment.status in (PaymentStatus.COMPLETED, PaymentStatus.REFUNDED):
        return payment  # already processed — ignore duplicate delivery (Stripe retries webhooks)

    payment.raw_callback = event

    if event_type == 'checkout.session.async_payment_failed':
        payment.status = PaymentStatus.FAILED
        payment.result_desc = 'Stripe reported async payment failure'
        payment.save()
        release_order_stock(payment.order, new_status=OrderStatus.CANCELLED)
        return payment

    if session.get('payment_status') != 'paid':
        # completed but not actually paid yet (e.g. still processing) — wait for the
        # follow-up async_payment_succeeded/failed event rather than fulfilling now.
        payment.save()
        return payment

    # Never trust the event alone — confirm the amount Stripe says was paid
    # actually matches what this order was charged before minting tickets.
    try:
        paid_amount = Decimal(int(session.get('amount_total', 0))) / 100
    except (TypeError, ValueError):
        paid_amount = None
    expected_amount = payment.amount

    if paid_amount != expected_amount or str(session.get('currency', '')).upper() != 'KES':
        logger.error(
            'Stripe session amount mismatch for %s: expected %s, got %s',
            session_id, expected_amount, paid_amount,
        )
        payment.status = PaymentStatus.FAILED
        payment.result_desc = 'Amount mismatch — payment not trusted'
        payment.save()
        release_order_stock(payment.order, new_status=OrderStatus.CANCELLED)
        return payment

    payment.stripe_payment_intent_id = session.get('payment_intent', '') or ''
    payment.status = PaymentStatus.COMPLETED
    payment.save()
    if payment.order.status != OrderStatus.PAID:
        try:
            fulfill_order(payment.order)
        except Exception:
            # Same reasoning as the M-Pesa path above — money confirmed, ticket
            # minting failed. Must not be silent.
            logger.exception(
                'fulfill_order failed after Stripe payment was confirmed for order %s (payment %s) — '
                'money received, no ticket minted. Needs manual reconciliation.',
                payment.order.reference, payment.pk,
            )
    return payment


@transaction.atomic
def handle_paystack_event(event: dict) -> Payment | None:
    """Process a signature-verified Paystack webhook event. Only charge.success
    triggers fulfilment; everything else is acknowledged and ignored."""
    if event.get('event') != 'charge.success':
        return None

    data = event.get('data', {})
    reference = data.get('reference')
    if not reference:
        logger.warning('Paystack charge.success event missing reference: %s', event)
        return None

    try:
        payment = Payment.objects.select_for_update().select_related('order').get(paystack_reference=reference)
    except Payment.DoesNotExist:
        logger.warning('Paystack event for unknown reference: %s', reference)
        return None

    if payment.status in (PaymentStatus.COMPLETED, PaymentStatus.REFUNDED):
        return payment  # already processed — ignore duplicate delivery (Paystack retries webhooks)

    payment.raw_callback = event

    if data.get('status') != 'success':
        payment.status = PaymentStatus.FAILED
        payment.result_desc = data.get('gateway_response', '')[:255]
        payment.save()
        release_order_stock(payment.order, new_status=OrderStatus.CANCELLED)
        return payment

    # Never trust the event alone — confirm the amount Paystack says was paid
    # actually matches what this order was charged before minting tickets.
    try:
        paid_amount = Decimal(int(data.get('amount', 0))) / 100
    except (TypeError, ValueError):
        paid_amount = None
    expected_amount = payment.amount

    if paid_amount != expected_amount or str(data.get('currency', '')).upper() != 'KES':
        logger.error(
            'Paystack event amount mismatch for %s: expected %s, got %s',
            reference, expected_amount, paid_amount,
        )
        payment.status = PaymentStatus.FAILED
        payment.result_desc = 'Amount mismatch — payment not trusted'
        payment.save()
        release_order_stock(payment.order, new_status=OrderStatus.CANCELLED)
        return payment

    payment.status = PaymentStatus.COMPLETED
    payment.save()
    if payment.order.status != OrderStatus.PAID:
        try:
            fulfill_order(payment.order)
        except Exception:
            logger.exception(
                'fulfill_order failed after Paystack payment was confirmed for order %s (payment %s) — '
                'money received, no ticket minted. Needs manual reconciliation.',
                payment.order.reference, payment.pk,
            )
    return payment
