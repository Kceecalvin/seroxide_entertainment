from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import Http404
from django.test import TestCase, RequestFactory, override_settings
from apps.accounts import demo
from apps.accounts.models import GateAssignment
from apps.events.models import Event
from apps.tickets.models import Order, Ticket


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class DemoAccountTests(TestCase):
    def test_seed_is_idempotent_and_creates_the_requested_roles(self):
        with patch('apps.accounts.management.commands.seed_demo_accounts.enabled', return_value=True):
            call_command('seed_demo_accounts', verbosity=0)
            tickets = Ticket.objects.count()
            call_command('seed_demo_accounts', verbosity=0)
        User = get_user_model()
        self.assertEqual(User.objects.filter(username__endswith='@demo.serotix.test').count(), 7)
        self.assertEqual(User.objects.filter(is_superuser=True).count(), 1)
        self.assertEqual(User.objects.filter(account_profile__role='admin').count(), 1)
        self.assertEqual(User.objects.filter(account_profile__role='scanner').count(), 3)
        self.assertEqual(Event.objects.filter(slug__startswith='demo-').count(), 5)
        self.assertEqual(Order.objects.filter(reference__startswith='SRX-DEMO').count(), 5)
        self.assertEqual(Ticket.objects.count(), tickets)
        self.assertEqual(GateAssignment.objects.count(), 4)
        self.assertTrue(User.objects.get(username='buyer@demo.serotix.test').check_password(demo.DEMO_PASSWORD))
        from apps.payments.models import Payment
        from apps.payments.refunds import issue_refund
        payment = Payment.objects.filter(status='completed').first()
        payment.method = 'paystack'
        payment.save(update_fields=['method'])
        with override_settings(DEBUG=True, REFUNDS_SIMULATE=True), patch('apps.payments.refunds.refund_transaction') as provider:
            issue_refund(payment)
            provider.assert_not_called()
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'refunded')
        self.assertTrue(payment.refund_reference.startswith('SIM-REFUND-'))

    @override_settings(LOCAL_DEMO_ENABLED=False)
    def test_seeding_and_quick_login_are_disabled_outside_demo(self):
        with self.assertRaises(CommandError):call_command('seed_demo_accounts')
        request = RequestFactory().post('/demo/switch/superadmin/')
        with self.assertRaises(Http404):demo.switch(request, 'superadmin')
        with self.assertRaises(Http404):demo.hub(RequestFactory().get('/demo/'))

    @override_settings(LOCAL_DEMO_ENABLED=True, DEBUG=True, EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend')
    def test_demo_refuses_real_email_backend_even_if_flag_is_set(self):
        self.assertFalse(demo.enabled())
        with self.assertRaises(CommandError):call_command('seed_demo_accounts')
