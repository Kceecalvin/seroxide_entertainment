"""Tests for payment integrity: webhook authentication, amount-tampering
protection, and duplicate-callback safety — the exact controls the security
audit checked for M-Pesa and (once added) Stripe.
"""
import hashlib
import hmac
import json
import time
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event, EventCategory
from apps.tickets.models import Order, OrderStatus, TicketStatus, TicketType
from apps.tickets.services import fulfill_order

from .models import Payment, PaymentMethod, PaymentStatus
from .paystack_client import PaystackSignatureError
from .paystack_client import verify_webhook_signature as verify_paystack_signature
from .refunds import RefundError, issue_refund
from .stripe_client import StripeSignatureError, verify_webhook_signature


def make_paid_setup(amount=500):
    from apps.tickets.services import create_order  # local import avoids a module-load cycle

    event = Event.objects.create(
        title='Test Event', description='d', venue='V', city='Nairobi',
        start_at=timezone.now() + timedelta(days=7), is_published=True,
        category=EventCategory.NIGHTLIFE,
    )
    ticket_type = TicketType.objects.create(event=event, name='Regular', price=amount, quantity_total=10)
    # Go through the real service so stock is actually reserved, same as a live checkout.
    order = create_order(
        event=event, buyer_name='A', buyer_email='', buyer_phone='254700000001',
        cart={str(ticket_type.pk): 1},
    )
    payment = Payment.objects.create(
        order=order, method=PaymentMethod.MPESA, phone_number='254700000001',
        amount=amount, checkout_request_id='ws_CO_test123',
    )
    return order, payment


def stk_payload(checkout_request_id, *, result_code=0, amount=500, receipt='TESTRCPT1'):
    return {
        'Body': {
            'stkCallback': {
                'CheckoutRequestID': checkout_request_id,
                'ResultCode': result_code,
                'ResultDesc': 'Success' if result_code == 0 else 'Cancelled by user',
                'CallbackMetadata': {
                    'Item': [
                        {'Name': 'Amount', 'Value': amount},
                        {'Name': 'MpesaReceiptNumber', 'Value': receipt},
                    ]
                } if result_code == 0 else {},
            }
        }
    }


class MpesaCallbackAuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.order, self.payment = make_paid_setup()

    def _callback_url(self, token):
        return reverse('payments:mpesa_callback', args=[token])

    @override_settings(MPESA_CALLBACK_TOKEN='correct-token')
    def test_wrong_token_is_rejected(self):
        resp = self.client.post(
            self._callback_url('wrong-token'),
            data=json.dumps(stk_payload('ws_CO_test123')),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PENDING, 'payment must not be touched on auth failure')

    @override_settings(MPESA_CALLBACK_TOKEN='correct-token')
    def test_correct_token_is_accepted_and_fulfills_order(self):
        resp = self.client.post(
            self._callback_url('correct-token'),
            data=json.dumps(stk_payload('ws_CO_test123')),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)

    @override_settings(MPESA_CALLBACK_TOKEN='')
    def test_unset_callback_token_rejects_everything(self):
        """An unconfigured token must fail closed, not open."""
        resp = self.client.post(
            self._callback_url('anything'),
            data=json.dumps(stk_payload('ws_CO_test123')),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(MPESA_CALLBACK_TOKEN='correct-token')
class MpesaAmountTamperingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.order, self.payment = make_paid_setup(amount=500)

    def test_amount_mismatch_is_rejected_and_stock_released(self):
        from apps.tickets.models import TicketType
        ticket_type = self.order.items.first().ticket_type
        before = ticket_type.quantity_sold

        resp = self.client.post(
            reverse('payments:mpesa_callback', args=['correct-token']),
            data=json.dumps(stk_payload('ws_CO_test123', amount=1)),  # claims KES 1 was paid, not 500
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)  # Daraja still gets a 200 ack
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertNotEqual(self.order.status, OrderStatus.PAID, 'a tampered amount must never fulfil an order')
        self.assertEqual(self.payment.status, PaymentStatus.FAILED)

        ticket_type.refresh_from_db()
        self.assertEqual(ticket_type.quantity_sold, before - 1, 'reserved stock must be released on rejection')

    def test_duplicate_callback_does_not_reprocess(self):
        url = reverse('payments:mpesa_callback', args=['correct-token'])
        self.client.post(url, data=json.dumps(stk_payload('ws_CO_test123')), content_type='application/json')
        self.order.refresh_from_db()
        first_ticket_count = self.order.items.first().tickets.count()

        # Safaricom redelivers the same callback
        self.client.post(url, data=json.dumps(stk_payload('ws_CO_test123')), content_type='application/json')
        self.order.refresh_from_db()
        second_ticket_count = self.order.items.first().tickets.count()
        self.assertEqual(first_ticket_count, second_ticket_count)

    def test_payment_failure_releases_reserved_stock(self):
        ticket_type = self.order.items.first().ticket_type
        before = ticket_type.quantity_sold
        self.client.post(
            reverse('payments:mpesa_callback', args=['correct-token']),
            data=json.dumps(stk_payload('ws_CO_test123', result_code=1)),  # user cancelled
            content_type='application/json',
        )
        ticket_type.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(ticket_type.quantity_sold, before - 1)
        self.assertEqual(self.order.status, OrderStatus.CANCELLED)


class StripeWebhookSignatureTests(TestCase):
    def _sign(self, payload_bytes, secret, timestamp=None):
        timestamp = timestamp or int(time.time())
        signed_payload = f'{timestamp}.'.encode() + payload_bytes
        sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return f't={timestamp},v1={sig}'

    def test_valid_signature_verifies(self):
        secret = 'whsec_test'
        payload = json.dumps({'type': 'checkout.session.completed'}).encode()
        header = self._sign(payload, secret)
        event = verify_webhook_signature(payload, header, secret)
        self.assertEqual(event['type'], 'checkout.session.completed')

    def test_tampered_payload_is_rejected(self):
        secret = 'whsec_test'
        payload = json.dumps({'type': 'checkout.session.completed'}).encode()
        header = self._sign(payload, secret)
        tampered = json.dumps({'type': 'checkout.session.completed', 'amount_total': 999999999}).encode()
        with self.assertRaises(StripeSignatureError):
            verify_webhook_signature(tampered, header, secret)

    def test_wrong_secret_is_rejected(self):
        payload = json.dumps({'type': 'checkout.session.completed'}).encode()
        header = self._sign(payload, 'whsec_real')
        with self.assertRaises(StripeSignatureError):
            verify_webhook_signature(payload, header, 'whsec_wrong')

    def test_stale_timestamp_is_rejected(self):
        secret = 'whsec_test'
        payload = json.dumps({'type': 'checkout.session.completed'}).encode()
        old_timestamp = int(time.time()) - 3600  # 1 hour old
        header = self._sign(payload, secret, timestamp=old_timestamp)
        with self.assertRaises(StripeSignatureError):
            verify_webhook_signature(payload, header, secret)

    def test_missing_header_is_rejected(self):
        with self.assertRaises(StripeSignatureError):
            verify_webhook_signature(b'{}', '', 'whsec_test')


class StripeCheckoutSessionTests(TestCase):
    """Regression coverage for a real bug found via live testing: the service
    fee (apps/tickets/models.py's Order.recalculate_total()) was charged to
    the buyer's order total but never added as its own Stripe line item, so
    Stripe's amount_total only ever matched the ticket subtotal — permanently
    tripping handle_stripe_event's amount check and cancelling every single
    real Stripe order regardless of whether the card payment succeeded."""

    @patch('apps.payments.stripe_client.requests.post')
    def test_line_items_total_matches_order_total_including_service_fee(self, mock_post):
        from apps.tickets.services import create_order
        from .stripe_client import create_checkout_session

        event = Event.objects.create(
            title='Fee Event', description='d', venue='V', city='Nairobi',
            start_at=timezone.now() + timedelta(days=7), is_published=True,
            category=EventCategory.NIGHTLIFE,
        )
        ticket_type = TicketType.objects.create(event=event, name='Regular', price=500, quantity_total=10)
        order = create_order(
            event=event, buyer_name='A', buyer_email='a@example.com', buyer_phone='254700000001',
            cart={str(ticket_type.pk): 1},
        )
        # Preserve regression coverage for already-issued historical orders.
        order.service_fee = Decimal('40.00')
        order.total_amount = Decimal('540.00')
        order.commission_rate = None
        order.platform_commission = Decimal('0.00')
        order.save()

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'id': 'cs_test_x', 'url': 'https://checkout.stripe.com/x'}

        create_checkout_session(order=order, success_url='https://x/success', cancel_url='https://x/cancel')

        sent = mock_post.call_args.kwargs['data']
        line_item_indices = {int(k.split('[')[1].split(']')[0]) for k in sent if k.startswith('line_items[')}
        cents_total = sum(
            sent[f'line_items[{i}][quantity]'] * sent[f'line_items[{i}][price_data][unit_amount]']
            for i in line_item_indices
        )
        self.assertEqual(cents_total, int(round(float(order.total_amount) * 100)))

    @override_settings(STRIPE_SIMULATE=False)
    @patch('apps.payments.stripe_client.requests.post')
    def test_full_webhook_flow_fulfills_order_when_amount_includes_service_fee(self, mock_post):
        """Not just a unit check on the request payload — proves the fee-inclusive
        line item actually satisfies handle_stripe_event's reconciliation end to end.
        STRIPE_SIMULATE must be forced off: dev/test settings default it to True,
        which bypasses create_checkout_session()/handle_stripe_event() entirely and
        would let this regression test pass even with the bug still present."""
        from apps.tickets.services import create_order
        from .services import initiate_stripe_payment, handle_stripe_event

        event = Event.objects.create(
            title='Fee Event 2', description='d', venue='V', city='Nairobi',
            start_at=timezone.now() + timedelta(days=7), is_published=True,
            category=EventCategory.NIGHTLIFE,
        )
        ticket_type = TicketType.objects.create(event=event, name='Regular', price=500, quantity_total=10)
        order = create_order(
            event=event, buyer_name='A', buyer_email='a@example.com', buyer_phone='254700000001',
            cart={str(ticket_type.pk): 1},
        )

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'id': 'cs_test_full', 'url': 'https://checkout.stripe.com/full'}
        payment, redirect_url = initiate_stripe_payment(
            order, success_url='https://x/success', cancel_url='https://x/cancel',
        )
        self.assertIsNotNone(redirect_url)

        # Derive amount_total the way Stripe itself would: by summing the line
        # items we actually submitted, not by reading order.total_amount again
        # — otherwise this "end to end" test can't fail even if the line items
        # sent to Stripe fall short of the order total.
        sent = mock_post.call_args.kwargs['data']
        line_item_indices = {int(k.split('[')[1].split(']')[0]) for k in sent if k.startswith('line_items[')}
        amount_total = sum(
            sent[f'line_items[{i}][quantity]'] * sent[f'line_items[{i}][price_data][unit_amount]']
            for i in line_item_indices
        )

        event_payload = {
            'type': 'checkout.session.completed',
            'data': {'object': {
                'id': 'cs_test_full',
                'payment_status': 'paid', 'currency': 'kes',
                'amount_total': amount_total,
                'payment_intent': 'pi_test_full',
            }},
        }
        handle_stripe_event(event_payload)

        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)
        self.assertEqual(order.status, OrderStatus.PAID)


class StripeWebhookEndpointTests(TestCase):
    def test_unconfigured_webhook_secret_rejects_everything(self):
        client = Client()
        with override_settings(STRIPE_WEBHOOK_SECRET=''):
            resp = client.post(
                reverse('payments:stripe_webhook'),
                data=json.dumps({'type': 'checkout.session.completed'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 403)

    def test_bad_signature_is_rejected(self):
        client = Client()
        with override_settings(STRIPE_WEBHOOK_SECRET='whsec_real'):
            resp = client.post(
                reverse('payments:stripe_webhook'),
                data=json.dumps({'type': 'checkout.session.completed'}),
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='t=123,v1=deadbeef',
            )
        self.assertEqual(resp.status_code, 400)


class PaystackWebhookSignatureTests(TestCase):
    def _sign(self, payload_bytes, secret):
        return hmac.new(secret.encode(), payload_bytes, hashlib.sha512).hexdigest()

    def test_valid_signature_verifies(self):
        secret = 'sk_test_123'
        payload = json.dumps({'event': 'charge.success'}).encode()
        sig = self._sign(payload, secret)
        event = verify_paystack_signature(payload, sig, secret)
        self.assertEqual(event['event'], 'charge.success')

    def test_tampered_payload_is_rejected(self):
        secret = 'sk_test_123'
        payload = json.dumps({'event': 'charge.success'}).encode()
        sig = self._sign(payload, secret)
        tampered = json.dumps({'event': 'charge.success', 'data': {'amount': 999999999}}).encode()
        with self.assertRaises(PaystackSignatureError):
            verify_paystack_signature(tampered, sig, secret)

    def test_wrong_secret_is_rejected(self):
        payload = json.dumps({'event': 'charge.success'}).encode()
        sig = self._sign(payload, 'sk_test_real')
        with self.assertRaises(PaystackSignatureError):
            verify_paystack_signature(payload, sig, 'sk_test_wrong')

    def test_missing_header_is_rejected(self):
        with self.assertRaises(PaystackSignatureError):
            verify_paystack_signature(b'{}', '', 'sk_test_123')


class PaystackWebhookEndpointTests(TestCase):
    def test_unconfigured_secret_key_rejects_everything(self):
        client = Client()
        with override_settings(PAYSTACK_SECRET_KEY=''):
            resp = client.post(
                reverse('payments:paystack_webhook'),
                data=json.dumps({'event': 'charge.success'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 403)

    def test_bad_signature_is_rejected(self):
        client = Client()
        with override_settings(PAYSTACK_SECRET_KEY='sk_test_real'):
            resp = client.post(
                reverse('payments:paystack_webhook'),
                data=json.dumps({'event': 'charge.success'}),
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE='deadbeef',
            )
        self.assertEqual(resp.status_code, 400)


class PaystackPaymentTests(TestCase):
    """Regression-shaped like StripeCheckoutSessionTests, but Paystack's single
    lump `amount` field (no itemized line items) means there's no equivalent of
    the missing-service-fee-line-item bug — this instead proves the amount sent
    already includes the fee, and exercises the full initiate->webhook->fulfil
    cycle end to end."""

    @override_settings(PAYSTACK_SIMULATE=False)
    @patch('apps.payments.paystack_client.requests.post')
    def test_initialize_amount_has_no_buyer_surcharge(self, mock_post):
        from apps.tickets.services import create_order

        from .services import initiate_paystack_payment

        event = Event.objects.create(
            title='Paystack Fee Event', description='d', venue='V', city='Nairobi',
            start_at=timezone.now() + timedelta(days=7), is_published=True,
            category=EventCategory.NIGHTLIFE,
        )
        ticket_type = TicketType.objects.create(event=event, name='Regular', price=500, quantity_total=10)
        order = create_order(
            event=event, buyer_name='A', buyer_email='a@example.com', buyer_phone='254700000001',
            cart={str(ticket_type.pk): 1},
        )
        self.assertEqual(order.service_fee, Decimal('0.00'))
        self.assertEqual(order.total_amount, Decimal('500.00'))
        self.assertEqual(order.platform_commission, Decimal('25.00'))

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'status': True, 'message': 'ok',
            'data': {'authorization_url': 'https://checkout.paystack.com/x', 'access_code': 'x', 'reference': 'x'},
        }
        initiate_paystack_payment(order, callback_url='https://x/pending')

        sent = mock_post.call_args.kwargs['json']
        self.assertEqual(sent['amount'], int(round(float(order.total_amount) * 100)))

    @override_settings(PAYSTACK_SIMULATE=False)
    @patch('apps.payments.paystack_client.requests.post')
    def test_full_webhook_flow_fulfills_order(self, mock_post):
        from apps.tickets.services import create_order

        from .services import handle_paystack_event, initiate_paystack_payment

        event = Event.objects.create(
            title='Paystack Fee Event 2', description='d', venue='V', city='Nairobi',
            start_at=timezone.now() + timedelta(days=7), is_published=True,
            category=EventCategory.NIGHTLIFE,
        )
        ticket_type = TicketType.objects.create(event=event, name='Regular', price=500, quantity_total=10)
        order = create_order(
            event=event, buyer_name='A', buyer_email='a@example.com', buyer_phone='254700000001',
            cart={str(ticket_type.pk): 1},
        )

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'status': True, 'message': 'ok',
            'data': {'authorization_url': 'https://checkout.paystack.com/x', 'access_code': 'x', 'reference': 'x'},
        }
        payment, redirect_url = initiate_paystack_payment(order, callback_url='https://x/pending')
        self.assertIsNotNone(redirect_url)

        event_payload = {
            'event': 'charge.success',
            'data': {
                'reference': payment.paystack_reference,
                'status': 'success', 'currency': 'KES',
                'amount': int(round(float(order.total_amount) * 100)),
            },
        }
        handle_paystack_event(event_payload)

        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)
        self.assertEqual(order.status, OrderStatus.PAID)

    @override_settings(PAYSTACK_SIMULATE=False)
    @patch('apps.payments.paystack_client.requests.post')
    def test_amount_mismatch_is_rejected_and_stock_released(self, mock_post):
        from apps.tickets.services import create_order

        from .services import handle_paystack_event, initiate_paystack_payment

        event = Event.objects.create(
            title='Paystack Fee Event 3', description='d', venue='V', city='Nairobi',
            start_at=timezone.now() + timedelta(days=7), is_published=True,
            category=EventCategory.NIGHTLIFE,
        )
        ticket_type = TicketType.objects.create(event=event, name='Regular', price=500, quantity_total=10)
        order = create_order(
            event=event, buyer_name='A', buyer_email='a@example.com', buyer_phone='254700000001',
            cart={str(ticket_type.pk): 1},
        )

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'status': True, 'message': 'ok',
            'data': {'authorization_url': 'https://checkout.paystack.com/x', 'access_code': 'x', 'reference': 'x'},
        }
        payment, _ = initiate_paystack_payment(order, callback_url='https://x/pending')

        handle_paystack_event({
            'event': 'charge.success',
            'data': {'reference': payment.paystack_reference, 'status': 'success', 'currency': 'KES', 'amount': 1},
        })

        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(order.status, OrderStatus.CANCELLED)


class IssueRefundTests(TestCase):
    def setUp(self):
        self.order, self.payment = make_paid_setup(amount=500)
        self.payment.status = PaymentStatus.COMPLETED
        self.payment.mpesa_receipt_number = 'TESTRCPT1'
        self.payment.save(update_fields=['status', 'mpesa_receipt_number'])
        fulfill_order(self.order)
        self.order.refresh_from_db()
        self.ticket_type = self.order.items.first().ticket_type

    def test_mpesa_refund_requires_manual_reference(self):
        with self.assertRaises(RefundError):
            issue_refund(self.payment, manual_reference='')

    def test_mpesa_refund_with_reference_cancels_order_and_voids_tickets(self):
        before_sold = self.ticket_type.quantity_sold
        issue_refund(self.payment, manual_reference='QJI7XXXX21')

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.ticket_type.refresh_from_db()

        self.assertEqual(self.payment.status, PaymentStatus.REFUNDED)
        self.assertEqual(self.payment.refund_reference, 'QJI7XXXX21')
        self.assertIsNotNone(self.payment.refunded_at)
        self.assertEqual(self.order.status, OrderStatus.CANCELLED)
        self.assertEqual(self.ticket_type.quantity_sold, before_sold - 1)
        for item in self.order.items.all():
            for ticket in item.tickets.all():
                self.assertEqual(ticket.status, TicketStatus.CANCELLED)

    def test_refund_is_idempotent(self):
        issue_refund(self.payment, manual_reference='QJI7XXXX21')
        self.payment.refresh_from_db()
        first_ref = self.payment.refund_reference
        # Second call must be a no-op — not raise, not double-release stock.
        issue_refund(self.payment, manual_reference='SOMETHING_ELSE')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.refund_reference, first_ref)

    def test_cannot_refund_non_completed_payment(self):
        self.payment.status = PaymentStatus.PENDING
        self.payment.save(update_fields=['status'])
        with self.assertRaises(RefundError):
            issue_refund(self.payment, manual_reference='ANYTHING')

    @patch('apps.payments.refunds.requests.post')
    def test_stripe_refund_calls_api_and_records_id(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'id': 're_test123'}

        order, payment = make_paid_setup(amount=500)
        payment.method = PaymentMethod.STRIPE
        payment.stripe_payment_intent_id = 'pi_test123'
        payment.status = PaymentStatus.COMPLETED
        payment.save(update_fields=['method', 'stripe_payment_intent_id', 'status'])
        fulfill_order(order)

        issue_refund(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.REFUNDED)
        self.assertEqual(payment.refund_reference, 're_test123')
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args.kwargs['data']['payment_intent'], 'pi_test123')

    @patch('apps.payments.refunds.requests.post')
    def test_stripe_refund_failure_raises_and_nothing_changes(self, mock_post):
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {'error': {'message': 'charge already refunded'}}

        order, payment = make_paid_setup(amount=500)
        payment.method = PaymentMethod.STRIPE
        payment.stripe_payment_intent_id = 'pi_test456'
        payment.status = PaymentStatus.COMPLETED
        payment.save(update_fields=['method', 'stripe_payment_intent_id', 'status'])

        with self.assertRaises(RefundError):
            issue_refund(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)


class PaymentStatusRateLimitTests(TestCase):
    """Pentest finding (SEC-05): this endpoint is intentionally unauthenticated
    (guest checkout has no session to check against), so a per-reference rate
    limit is the actual mitigation — repeatedly polling one reference is
    capped, while checking many different real orders' own status isn't."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = Client()
        self.order, _ = make_paid_setup()

    def test_repeated_polling_of_one_reference_is_capped(self):
        url = reverse('payments:status', args=[self.order.reference])
        for _ in range(30):
            self.client.get(url)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 429)

    def test_checking_a_different_order_is_not_blocked_by_another_ones_cap(self):
        order_a = self.order
        order_b, _ = make_paid_setup(amount=1000)
        url_a = reverse('payments:status', args=[order_a.reference])
        session = self.client.session
        session['ticket_orders'] = [order_a.reference, order_b.reference]
        session.save()
        url_b = reverse('payments:status', args=[order_b.reference])
        for _ in range(30):
            self.client.get(url_a)
        resp = self.client.get(url_b)
        self.assertEqual(resp.status_code, 200)
