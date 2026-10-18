from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.tickets.models import TicketType
from .models import Event


class DiscoveryExperienceTests(TestCase):
    def event(self, title='Live at the coast', **overrides):
        fields = dict(title=title, description='A night by the ocean.', venue='Beach stage', city='Kilifi', start_at=timezone.now() + timedelta(days=7), category='festival')
        fields.update(overrides)
        event = Event.objects.create(**fields)
        TicketType.objects.create(event=event, name='General admission', price=Decimal('2000.50'), quantity_total=50)
        return event

    def test_search_includes_city_and_keeps_filter_values(self):
        self.event()
        response = self.client.get('/', {'q': 'Kilifi', 'city': 'Kilifi', 'when': 'month'})
        self.assertContains(response, 'Live at the coast')
        self.assertEqual(response.context['selected_city'], 'Kilifi')
        self.assertIn('city=Kilifi', response.context['category_links'][0]['url'])
        self.assertIn('when=month', response.context['category_links'][0]['url'])

    def test_default_listing_hides_past_and_unpublished_events(self):
        self.event('Coming soon')
        self.event('Past show', start_at=timezone.now() - timedelta(days=1))
        self.event('Private show', is_published=False)
        response = self.client.get('/')
        self.assertContains(response, 'Coming soon')
        self.assertNotContains(response, 'Past show')
        self.assertNotContains(response, 'Private show')
        self.assertEqual(response.context['result_count'], 1)

    def test_weekend_on_sunday_includes_today_and_excludes_next_week(self):
        sunday = timezone.make_aware(timezone.datetime(2026, 9, 20, 10))
        with patch('apps.events.views.timezone.now', return_value=sunday):
            self.event('Sunday show', start_at=sunday + timedelta(hours=5))
            self.event('Next Friday', start_at=sunday + timedelta(days=5))
            response = self.client.get('/', {'when': 'weekend'})
        titles = [event.title for event in response.context['events']]
        self.assertEqual(titles, ['Sunday show'])

    def test_month_filter_handles_december_rollover(self):
        december = timezone.make_aware(timezone.datetime(2026, 12, 20, 10))
        with patch('apps.events.views.timezone.now', return_value=december):
            self.event('December show', start_at=december + timedelta(days=2))
            self.event('January show', start_at=december + timedelta(days=20))
            response = self.client.get('/', {'when': 'month'})
        self.assertEqual([e.title for e in response.context['events']], ['December show'])

    def test_featured_ticket_uses_featured_event_cover_and_actual_link(self):
        event = self.event('Featured festival', is_featured=True, cover_image='events/covers/real-cover.jpg')
        response = self.client.get('/')
        self.assertEqual(response.context['next_event'], event)
        self.assertContains(response, '/media/events/covers/real-cover.jpg')
        self.assertContains(response, event.get_absolute_url())
        self.assertNotContains(response, 'karibu-campus-hero.jpg')

    def test_pagination_retains_search(self):
        for index in range(14):
            self.event(f'Festival {index}')
        response = self.client.get('/', {'q': 'Festival', 'page': 2})
        self.assertEqual(response.context['result_count'], 14)
        self.assertEqual(len(response.context['events']), 2)
        self.assertContains(response, 'q=Festival&amp;page=1')

    def test_prefetched_card_prices_and_stock_do_not_query_per_property(self):
        event = self.event()
        TicketType.objects.create(event=event, name='Expired offer', price=1, quantity_total=10, sales_end=timezone.now() - timedelta(days=1))
        TicketType.objects.create(event=event, name='Hidden tier', price=2, quantity_total=20, is_active=False)
        prefetched = Event.objects.prefetch_related('ticket_types').get(pk=event.pk)
        with self.assertNumQueries(0):
            self.assertEqual(prefetched.min_price, Decimal('2000.50'))
            self.assertEqual(prefetched.total_remaining, 50)
            self.assertFalse(prefetched.is_sold_out)

    def test_detail_has_safe_checkout_data_and_correct_absolute_share_image(self):
        event = self.event(title='A "special" <night>', cover_image='events/covers/real-cover.jpg')
        response = self.client.get(event.get_absolute_url())
        self.assertContains(response, 'http://testserver/media/events/covers/real-cover.jpg')
        self.assertContains(response, 'id="checkout-data"')
        self.assertContains(response, r'\u003Cnight\u003E')
        data = response.context['checkout_data']
        self.assertEqual(data['checkoutUrl'], reverse('tickets:checkout', args=[event.slug]))
        self.assertEqual(data['types'][0]['price'], 2000.5)
        self.assertTrue(data['csrfToken'])
        self.assertContains(response, 'name="qty_')  # HTML fallback is real, not a loading placeholder.

    def test_past_event_has_no_purchase_mount(self):
        event = self.event(start_at=timezone.now() - timedelta(days=1))
        response = self.client.get(event.get_absolute_url())
        self.assertContains(response, "This one's a memory.")
        self.assertNotContains(response, 'id="ticket-checkout"')

    def test_all_closed_sales_cannot_be_selected(self):
        event = self.event()
        event.ticket_types.update(sales_end=timezone.now() - timedelta(hours=1))
        response = self.client.get(event.get_absolute_url())
        self.assertTrue(response.context['checkout_data']['types'][0]['sales_closed'])
        self.assertContains(response, 'Sales ended')

    def test_catalog_excludes_private_and_past_events_and_has_no_buyer_data(self):
        event = self.event('Public event')
        self.event('Private event', is_published=False)
        self.event('Old event', start_at=timezone.now() - timedelta(days=1))
        response = self.client.get(reverse('events:catalog'))
        records = response.json()['events']
        self.assertEqual([item['title'] for item in records], ['Public event'])
        self.assertEqual(records[0]['url'], event.get_absolute_url())
        self.assertNotIn('buyer_email', response.content.decode())
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_squad_catalog_is_bounded_and_revalidates_slugs(self):
        events = [self.event(f'Squad event {i}') for i in range(10)]
        response = self.client.get(reverse('events:catalog'), {'slugs': ','.join(e.slug for e in events)})
        self.assertEqual(len(response.json()['events']), 8)
        empty = self.client.get(reverse('events:catalog'), {'slugs': ''})
        self.assertEqual(empty.json()['events'], [])

    def test_from_price_uses_available_stock_instead_of_sold_out_early_bird(self):
        event = self.event()
        TicketType.objects.create(event=event, name='Sold out early bird', price=500, quantity_total=10, quantity_sold=10)
        self.assertEqual(event.min_price, Decimal('2000.50'))
