from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.events.models import Event
from apps.tickets.models import Order, TicketType
from .availability import available_methods


class ProductionAvailabilityTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(title='Release fixture', slug='release-fixture',
            venue='Test venue', city='Nairobi', start_at=timezone.now()+timedelta(days=7))
        self.tier = TicketType.objects.create(event=self.event, name='General', price=1000, quantity_total=2)

    @override_settings(PAYMENTS_REQUIRE_LIVE=True, PAYMENTS_LIVE=False)
    def test_checkout_disabled_before_any_stock_or_provider_mutation(self):
        with patch('apps.tickets.views.initiate_payment') as provider:
            response = self.client.post(reverse('tickets:checkout',args=[self.event.slug]), {
                'buyer_name':'Test Buyer','buyer_phone':'0712345678','buyer_email':'buyer@example.test',
                'payment_method':'mpesa','terms_accepted':'on',f'qty_{self.tier.pk}':'1'})
        self.assertEqual(response.status_code,302)
        provider.assert_not_called()
        self.assertEqual(Order.objects.count(),0)
        self.tier.refresh_from_db()
        self.assertEqual(self.tier.quantity_sold,0)
        page=self.client.get(self.event.get_absolute_url())
        self.assertContains(page,'Booking opens soon.')
        self.assertNotContains(page,'id="checkout-data"')

    @override_settings(PAYMENTS_REQUIRE_LIVE=True,PAYMENTS_LIVE=True,MPESA_ENV='sandbox',
        MPESA_SIMULATE=False,PAYSTACK_SIMULATE=False,PAYSTACK_SECRET_KEY='sk_test_example',PAYSTACK_PUBLIC_KEY='pk_test_example')
    def test_live_toggle_cannot_enable_test_providers(self):
        self.assertEqual(available_methods(),())

    @override_settings(PAYMENTS_REQUIRE_LIVE=True,PAYMENTS_LIVE=True,MPESA_ENV='sandbox',
        PAYSTACK_SECRET_KEY='sk_live_example',PAYSTACK_PUBLIC_KEY='pk_live_example')
    def test_only_live_hosted_card_provider_is_offered(self):
        self.assertEqual(available_methods(),('paystack',))
        page=self.client.get(self.event.get_absolute_url())
        self.assertContains(page,'"mpesaEnabled": false')
        self.assertContains(page,'value="paystack"')

    def test_retired_card_endpoints_are_not_routed(self):
        self.assertEqual(self.client.post('/payments/card/charge/SRX-TEST/').status_code,404)
        self.assertEqual(self.client.get('/tickets/order/SRX-TEST/pay/card/').status_code,404)
        self.assertEqual(self.client.post('/payments/flutterwave/webhook/').status_code,404)
