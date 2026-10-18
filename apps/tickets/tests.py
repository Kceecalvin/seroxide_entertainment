"""Tests for the business-logic guarantees the security audit flagged:
stock can't be oversold, a duplicated payment callback can't double-mint
tickets, and door check-in can't double-admit the same QR code.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event, EventCategory

from .models import Order, OrderStatus, Ticket, TicketStatus, TicketType, WaitlistEntry
from .services import OrderError, create_order, fulfill_order, release_order_stock

User = get_user_model()


def make_event(**overrides):
    defaults = dict(
        title='Test Event', description='desc', venue='Test Venue', city='Nairobi',
        start_at=timezone.now() + timedelta(days=7), is_published=True,
        category=EventCategory.NIGHTLIFE,
    )
    defaults.update(overrides)
    return Event.objects.create(**defaults)


class StockReservationTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.ticket_type = TicketType.objects.create(
            event=self.event, name='Regular', price=500, quantity_total=2,
        )

    def test_create_order_reserves_stock_immediately(self):
        self.assertEqual(self.ticket_type.remaining, 2)
        create_order(
            event=self.event, buyer_name='A', buyer_email='', buyer_phone='254700000001',
            cart={str(self.ticket_type.pk): 1},
        )
        self.ticket_type.refresh_from_db()
        self.assertEqual(self.ticket_type.quantity_sold, 1)
        self.assertEqual(self.ticket_type.remaining, 1)

    def test_cannot_oversell_past_quantity_total(self):
        create_order(
            event=self.event, buyer_name='A', buyer_email='', buyer_phone='254700000001',
            cart={str(self.ticket_type.pk): 2},
        )
        with self.assertRaises(OrderError):
            create_order(
                event=self.event, buyer_name='B', buyer_email='', buyer_phone='254700000002',
                cart={str(self.ticket_type.pk): 1},
            )

    def test_release_order_stock_gives_reservation_back(self):
        order = create_order(
            event=self.event, buyer_name='A', buyer_email='', buyer_phone='254700000001',
            cart={str(self.ticket_type.pk): 2},
        )
        release_order_stock(order, new_status=OrderStatus.CANCELLED)
        self.ticket_type.refresh_from_db()
        self.assertEqual(self.ticket_type.quantity_sold, 0)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)

    def test_release_order_stock_is_a_noop_on_a_paid_order(self):
        """Guards against ever accidentally un-reserving stock for a real sale."""
        order = create_order(
            event=self.event, buyer_name='A', buyer_email='', buyer_phone='254700000001',
            cart={str(self.ticket_type.pk): 1},
        )
        fulfill_order(order)
        release_order_stock(order, new_status=OrderStatus.CANCELLED)
        order.refresh_from_db()
        self.ticket_type.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)  # unchanged
        self.assertEqual(self.ticket_type.quantity_sold, 1)  # unchanged


class FulfillOrderIdempotencyTests(TestCase):
    """The exact bug the security audit found: fulfill_order() must be safe
    to call twice for the same order (a duplicated M-Pesa/Stripe callback)."""

    def setUp(self):
        self.event = make_event()
        self.ticket_type = TicketType.objects.create(
            event=self.event, name='Regular', price=500, quantity_total=10,
        )
        self.order = create_order(
            event=self.event, buyer_name='A', buyer_email='a@example.com', buyer_phone='254700000001',
            cart={str(self.ticket_type.pk): 2},
        )

    def test_second_call_does_not_double_mint_tickets(self):
        fulfill_order(self.order)
        first_count = Ticket.objects.filter(order_item__order=self.order).count()
        self.assertEqual(first_count, 2)

        fulfill_order(self.order)  # simulate a duplicated callback
        second_count = Ticket.objects.filter(order_item__order=self.order).count()
        self.assertEqual(second_count, 2, 'fulfill_order() minted extra tickets on a duplicate call')

    def test_second_call_does_not_double_count_stock(self):
        fulfill_order(self.order)
        fulfill_order(self.order)
        self.ticket_type.refresh_from_db()
        self.assertEqual(self.ticket_type.quantity_sold, 2)

    def test_fulfill_order_sends_confirmation_email(self):
        # fulfill_order() defers the send via transaction.on_commit(), which
        # TestCase's per-test transaction never actually commits — so it must
        # be triggered explicitly here rather than expected to fire on its own.
        with self.captureOnCommitCallbacks(execute=True):
            fulfill_order(self.order)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('a@example.com', mail.outbox[0].to)
        self.assertEqual(len(mail.outbox[0].attachments), 2, 'expected one inline QR image per ticket')


class ScannerCheckInTests(TestCase):
    """The other race the audit found: two near-simultaneous scans of the
    same QR must not both succeed."""

    def setUp(self):
        self.staff = User.objects.create_user(username='door', password='x', is_staff=True)
        self.event = make_event()
        from apps.accounts.models import GateAssignment
        GateAssignment.objects.create(user=self.staff, event=self.event)
        self.ticket_type = TicketType.objects.create(
            event=self.event, name='Regular', price=500, quantity_total=5,
        )
        self.order = create_order(
            event=self.event, buyer_name='A', buyer_email='', buyer_phone='254700000001',
            cart={str(self.ticket_type.pk): 1},
        )
        fulfill_order(self.order)
        self.ticket = Ticket.objects.filter(order_item__order=self.order).first()
        self.client = Client()
        self.client.force_login(self.staff)

    def _scan(self):
        return self.client.post(reverse('tickets:scanner_check', args=[self.ticket.serial]))

    def test_first_scan_checks_in(self):
        resp = self._scan()
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['result'], TicketStatus.USED)

    def test_second_scan_is_rejected_as_already_used(self):
        self._scan()
        resp = self._scan()
        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertEqual(data['result'], 'already_used')

    def test_unknown_serial_returns_not_found(self):
        import uuid
        resp = self.client.post(reverse('tickets:scanner_check', args=[uuid.uuid4()]))
        self.assertEqual(resp.status_code, 404)

    def test_scanner_requires_staff_login(self):
        anon_client = Client()
        resp = anon_client.post(reverse('tickets:scanner_check', args=[self.ticket.serial]))
        self.assertNotEqual(resp.status_code, 200)


@override_settings(MPESA_SIMULATE=True)
class CheckoutFlowTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # the rate-limit test in this class must not leak into its siblings
        self.event = make_event()
        self.ticket_type = TicketType.objects.create(
            event=self.event, name='Regular', price=500, quantity_total=5,
        )
        self.client = Client()

    def test_guest_checkout_without_consent_creates_no_order(self):
        self.client.post(reverse('tickets:checkout', args=[self.event.slug]), {
            f'qty_{self.ticket_type.pk}': 1,
            'buyer_name': 'No Consent', 'buyer_email': '', 'buyer_phone': '254700000001',
            'payment_method': 'mpesa',
            # terms_accepted intentionally omitted
        })
        self.assertEqual(Order.objects.filter(buyer_name='No Consent').count(), 0)

    def test_guest_checkout_with_consent_creates_order(self):
        self.client.post(reverse('tickets:checkout', args=[self.event.slug]), {
            f'qty_{self.ticket_type.pk}': 1,
            'buyer_name': 'Consented', 'buyer_email': '', 'buyer_phone': '254700000001',
            'payment_method': 'mpesa', 'terms_accepted': 'on',
        })
        self.assertEqual(Order.objects.filter(buyer_name='Consented').count(), 1)

    def test_checkout_links_order_to_authenticated_buyer(self):
        user = User.objects.create_user(username='buyer@example.com', password='x', email='buyer@example.com')
        self.client.force_login(user)
        self.client.post(reverse('tickets:checkout', args=[self.event.slug]), {
            f'qty_{self.ticket_type.pk}': 1,
            'buyer_name': 'Logged In', 'buyer_email': 'buyer@example.com', 'buyer_phone': '254700000001',
            'payment_method': 'mpesa',
        })
        order = Order.objects.get(buyer_name='Logged In')
        self.assertEqual(order.buyer_id, user.id)

    def test_checkout_is_rate_limited(self):
        """Pentest finding (SEC-02): checkout reserves real stock on every
        POST, so unlike a pure lookup endpoint it must never be unthrottled —
        an unbounded loop here is a real stock-exhaustion attack."""
        from django.core.cache import cache
        cache.clear()
        data = {
            f'qty_{self.ticket_type.pk}': 1,
            'buyer_name': 'Spammer', 'buyer_email': '', 'buyer_phone': '254700000001',
            'payment_method': 'mpesa', 'terms_accepted': 'on',
        }
        for _ in range(20):
            self.client.post(reverse('tickets:checkout', args=[self.event.slug]), data)
        resp = self.client.post(reverse('tickets:checkout', args=[self.event.slug]), data)
        self.assertEqual(resp.status_code, 429)


class CommissionTests(TestCase):
    def setUp(self):
        self.event = make_event()

    def order(self, price='1000.00', quantity=1):
        tier = TicketType.objects.create(event=self.event, name='General', price=price, quantity_total=100)
        return create_order(event=self.event, buyer_name='Buyer', buyer_email='buyer@example.test',
                            buyer_phone='254700000001', cart={tier.pk: quantity})

    def test_five_percent_is_deducted_not_added(self):
        order = self.order()
        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal('1000.00'))
        self.assertEqual(order.service_fee, Decimal('0.00'))
        self.assertEqual(order.commission_rate, Decimal('0.05'))
        self.assertEqual(order.platform_commission, Decimal('50.00'))
        self.assertEqual(order.organizer_share, Decimal('950.00'))

    def test_cent_rounding_reconciles_and_rate_is_snapshotted(self):
        order = self.order('333.33', quantity=3)
        with override_settings(PLATFORM_COMMISSION_RATE=Decimal('0.10')):
            order.recalculate_total()
        self.assertEqual(order.total_amount, Decimal('999.99'))
        self.assertEqual(order.platform_commission, Decimal('50.00'))
        self.assertEqual(order.organizer_share, Decimal('949.99'))
        self.assertEqual(order.organizer_share + order.platform_commission, order.total_amount)

    def test_half_cent_rounds_up(self):
        order = self.order('0.10')
        self.assertEqual(order.platform_commission, Decimal('0.01'))
        self.assertEqual(order.organizer_share, Decimal('0.09'))

    def test_old_buyer_fee_setting_cannot_add_a_surcharge(self):
        with override_settings(SERVICE_FEE_PERCENT=0.08):
            order = self.order()
        self.assertEqual(order.service_fee, 0)
        self.assertEqual(order.total_amount, 1000)

    def test_historical_order_retains_original_amounts(self):
        order = Order.objects.create(event=self.event, buyer_name='Historical', buyer_phone='254700000001',
                                     total_amount=1080, service_fee=80)
        with self.assertRaises(ValueError):
            order.recalculate_total()
        order.refresh_from_db()
        self.assertEqual(order.total_amount, 1080)
        self.assertEqual(order.service_fee, 80)
        self.assertEqual(order.platform_commission, 0)
        self.assertIsNone(order.commission_rate)

    def test_payment_attempt_and_paid_order_cannot_be_repriced(self):
        from apps.payments.models import Payment
        order = self.order()
        Payment.objects.create(order=order, amount=order.total_amount, method='mpesa')
        with self.assertRaises(ValueError):
            order.recalculate_total()
        order = self.order()
        order.status = OrderStatus.PAID
        order.save(update_fields=['status'])
        with self.assertRaises(ValueError):
            order.recalculate_total()

    def test_mpesa_receives_ticket_total_without_buyer_fee(self):
        from apps.payments.services import initiate_payment
        from apps.payments.models import Payment
        order = self.order()
        with override_settings(MPESA_SIMULATE=True):
            initiate_payment(order, phone_number='254700000001')
        self.assertEqual(Payment.objects.get(order=order).amount, 1000)

    def test_receipt_displays_included_processing_and_official_phone(self):
        from django.template.loader import render_to_string
        from apps.tickets.emails import _deliver_order_confirmation
        order = self.order()
        _deliver_order_confirmation(order)
        message = mail.outbox[-1]
        self.assertIn('Payment processing included.', message.body)
        self.assertIn('0119 300000', message.body)
        self.assertIn('tel:+254119300000', message.alternatives[0].content)
        self.assertNotIn('Service fee:', message.body)
        order.service_fee = Decimal('80.00')
        order.total_amount = Decimal('1080.00')
        old_receipt = render_to_string('emails/order_confirmation.txt', {'order': order})
        self.assertIn('Service fee: KES 80.00', old_receipt)


class WaitlistTests(TestCase):
    """Covers the sold-out demand-capture flow: joining, and being notified
    (once, oldest-first) exactly when stock actually frees up."""

    def setUp(self):
        self.event = make_event()
        self.ticket_type = TicketType.objects.create(event=self.event, name='VIP', price=1000, quantity_total=1)
        self.client = Client()

    def test_join_waitlist_creates_entry(self):
        resp = self.client.post(reverse('tickets:join_waitlist', args=[self.ticket_type.pk]), {
            'name': 'Jane Wanjiku', 'email': 'jane@example.com', 'phone': '',
        })
        self.assertRedirects(resp, self.event.get_absolute_url())
        entry = WaitlistEntry.objects.get(ticket_type=self.ticket_type)
        self.assertEqual(entry.email, 'jane@example.com')
        self.assertIsNone(entry.notified_at)

    def test_invalid_email_is_rejected(self):
        self.client.post(reverse('tickets:join_waitlist', args=[self.ticket_type.pk]), {
            'name': 'Jane', 'email': 'not-an-email', 'phone': '',
        })
        self.assertEqual(WaitlistEntry.objects.count(), 0)

    def test_notify_waitlist_does_nothing_while_sold_out(self):
        from .services import notify_waitlist
        WaitlistEntry.objects.create(ticket_type=self.ticket_type, name='Jane', email='jane@example.com')
        self.ticket_type.quantity_sold = 1  # fully sold — remaining == 0
        self.ticket_type.save(update_fields=['quantity_sold'])
        notify_waitlist(self.ticket_type)
        self.assertEqual(len(mail.outbox), 0)
        entry = WaitlistEntry.objects.get()
        self.assertIsNone(entry.notified_at)

    def test_notify_waitlist_emails_oldest_first_up_to_remaining(self):
        from .services import notify_waitlist
        first = WaitlistEntry.objects.create(ticket_type=self.ticket_type, name='First', email='first@example.com')
        WaitlistEntry.objects.create(ticket_type=self.ticket_type, name='Second', email='second@example.com')
        # quantity_sold=0 on a quantity_total=1 type -> exactly 1 spot free
        with self.captureOnCommitCallbacks(execute=True):
            notify_waitlist(self.ticket_type)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['first@example.com'])
        first.refresh_from_db()
        self.assertIsNotNone(first.notified_at)
        second = WaitlistEntry.objects.get(email='second@example.com')
        self.assertIsNone(second.notified_at)

    def test_already_notified_entries_are_not_re_notified(self):
        from .services import notify_waitlist
        entry = WaitlistEntry.objects.create(
            ticket_type=self.ticket_type, name='Jane', email='jane@example.com', notified_at=timezone.now(),
        )
        notify_waitlist(self.ticket_type)
        self.assertEqual(len(mail.outbox), 0)

    def test_refund_of_a_paid_order_notifies_the_waitlist(self):
        """End-to-end: a real refund frees a real spot, and the person
        waiting for it actually gets emailed — not just the unit-level
        notify_waitlist() call in isolation."""
        from apps.payments.models import Payment, PaymentMethod, PaymentStatus
        from apps.payments.refunds import issue_refund

        order = create_order(
            event=self.event, buyer_name='Buyer', buyer_email='', buyer_phone='254700000001',
            cart={str(self.ticket_type.pk): 1},
        )
        payment = Payment.objects.create(
            order=order, method=PaymentMethod.MPESA, phone_number='254700000001',
            amount=order.total_amount, status=PaymentStatus.COMPLETED,
        )
        with self.captureOnCommitCallbacks(execute=True):
            fulfill_order(order)

        WaitlistEntry.objects.create(ticket_type=self.ticket_type, name='Jane', email='jane@example.com')
        mail.outbox.clear()

        with self.captureOnCommitCallbacks(execute=True):
            issue_refund(payment, manual_reference='TEST123')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['jane@example.com'])

    def test_abandoned_order_expiry_notifies_the_waitlist(self):
        """The other stock-release path: an order that never gets a payment
        callback at all (release_order_stock, not a refund) must also
        trigger waitlist notifications once its reserved stock is freed."""
        order = create_order(
            event=self.event, buyer_name='Buyer', buyer_email='', buyer_phone='254700000001',
            cart={str(self.ticket_type.pk): 1},
        )
        WaitlistEntry.objects.create(ticket_type=self.ticket_type, name='Jane', email='jane@example.com')
        with self.captureOnCommitCallbacks(execute=True):
            release_order_stock(order, new_status=OrderStatus.EXPIRED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['jane@example.com'])
