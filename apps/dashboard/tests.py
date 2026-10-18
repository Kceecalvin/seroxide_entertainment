"""Role-separation tests: is_staff alone must reach the scanner and nothing
else staff-only; is_superuser is required for the organizer dashboard."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class RoleSeparationTests(TestCase):
    def setUp(self):
        self.gateman = User.objects.create_user(username='gateman', password='x', is_staff=True, is_superuser=False)
        self.admin = User.objects.create_user(username='admin2', password='x', is_staff=True, is_superuser=True)
        self.buyer = User.objects.create_user(username='buyer', password='x')
        self.client = Client()

    def test_gateman_can_reach_scanner(self):
        self.client.force_login(self.gateman)
        resp = self.client.get(reverse('tickets:scanner'))
        self.assertEqual(resp.status_code, 200)

    def test_gateman_cannot_reach_dashboard(self):
        self.client.force_login(self.gateman)
        resp = self.client.get(reverse('dashboard:home'))
        self.assertNotEqual(resp.status_code, 200)

    def test_gateman_cannot_reach_payment_reconciliation(self):
        self.client.force_login(self.gateman)
        resp = self.client.get(reverse('dashboard:payment_reconciliation'))
        self.assertNotEqual(resp.status_code, 200)

    def test_admin_can_reach_dashboard(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('dashboard:home'))
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_reach_scanner_too(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('tickets:scanner'))
        self.assertEqual(resp.status_code, 200)

    def test_plain_buyer_cannot_reach_scanner_or_dashboard(self):
        self.client.force_login(self.buyer)
        self.assertNotEqual(self.client.get(reverse('tickets:scanner')).status_code, 200)
        self.assertNotEqual(self.client.get(reverse('dashboard:home')).status_code, 200)

    def test_anonymous_cannot_reach_either(self):
        self.assertNotEqual(self.client.get(reverse('tickets:scanner')).status_code, 200)
        self.assertNotEqual(self.client.get(reverse('dashboard:home')).status_code, 200)

    def test_login_redirects_gateman_to_scanner_not_dashboard(self):
        resp = self.client.post(reverse('dashboard:login'), {'username': 'gateman', 'password': 'x'})
        self.assertRedirects(resp, reverse('tickets:scanner'))

    def test_login_redirects_admin_to_dashboard(self):
        resp = self.client.post(reverse('dashboard:login'), {'username': 'admin2', 'password': 'x'})
        self.assertRedirects(resp, reverse('dashboard:home'))


class PaidRevenueReportingTests(TestCase):
    def test_dashboard_uses_paid_order_prices_and_excludes_reservations(self):
        from datetime import timedelta
        from decimal import Decimal
        from django.utils import timezone
        from apps.events.models import Event
        from apps.tickets.models import Order, OrderItem, OrderStatus, TicketType

        admin = User.objects.create_user(username='metrics-admin', is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        event = Event.objects.create(title='Revenue event', venue='Nairobi', description='Live', start_at=timezone.now() + timedelta(days=3))
        tier = TicketType.objects.create(event=event, name='General', price=9000, quantity_total=100, quantity_sold=20)
        paid = Order.objects.create(event=event, buyer_name='Test', buyer_phone='254700000001', status=OrderStatus.PAID, total_amount=2160, service_fee=160)
        OrderItem.objects.create(order=paid, ticket_type=tier, quantity=2, unit_price=1000)
        pending = Order.objects.create(event=event, buyer_name='Pending', buyer_phone='254700000002', total_amount=5400, service_fee=400)
        OrderItem.objects.create(order=pending, ticket_type=tier, quantity=5, unit_price=1000)
        Order.objects.create(event=event, buyer_name='Refunded', buyer_phone='254700000003', status=OrderStatus.CANCELLED, total_amount=1080, service_fee=80)
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.context['metrics']['ticket_sales'], Decimal('2000'))
        self.assertEqual(response.context['metrics']['platform_fees'], Decimal('160'))
        self.assertEqual(response.context['metrics']['average_order'], Decimal('2160'))
        self.assertEqual(response.context['metrics']['paid_orders'], 1)
        self.assertEqual(response.context['metrics']['pending_orders'], 1)
        self.assertEqual(response.context['rows'][0]['sold'], 2)
        self.assertEqual(response.context['rows'][0]['revenue'], Decimal('2000'))
