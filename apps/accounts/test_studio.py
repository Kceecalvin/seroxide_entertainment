from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountProfile
from apps.events.models import Event
from apps.tickets.models import Order, TicketType


class OrganizerStudioTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user('studio-owner', password='TestStudio123!')
        self.other = get_user_model().objects.create_user('studio-other', password='TestStudio123!')
        AccountProfile.objects.create(user=self.owner, role='seller', business_name='Studio A')
        AccountProfile.objects.create(user=self.other, role='seller', business_name='Studio B')
        self.event = Event.objects.create(owner=self.owner, title='My festival', venue='Coast Stage', city='Kilifi',
            description='The experience', start_at=timezone.now()+timedelta(days=10), review_status='draft',
            is_published=False, cover_image='events/covers/test.jpg')
        self.foreign = Event.objects.create(owner=self.other, title='Another client festival', venue='Coast Stage',
            start_at=timezone.now()+timedelta(days=10), review_status='draft', is_published=False)
        self.client.force_login(self.owner)

    def test_search_status_and_pagination_never_expose_another_organizer(self):
        for data in [{'q':'festival'}, {'q':'Coast'}, {'status':'draft'}, {'status':'invalid'}, {'page':'invalid'}]:
            response = self.client.get(reverse('accounts:seller_home'), data)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, self.foreign.title)
            self.assertContains(response, self.event.title)
        self.assertNotContains(self.client.get(reverse('accounts:seller_home'), {'status':'live'}), self.event.title)
        for n in range(13):
            Event.objects.create(owner=self.owner, title=f'Draft {n}', venue='Hall',
                start_at=timezone.now()+timedelta(days=10), review_status='draft')
        response = self.client.get(reverse('accounts:seller_home'), {'status':'draft','page':'2'})
        self.assertEqual(len(response.context['events']), 2)
        self.assertEqual(response.context['event_count'], 14)

    def test_filtered_dashboard_keeps_all_event_totals_and_excludes_other_clients(self):
        for event, amount in [(self.event, 1000), (self.foreign, 5000)]:
            Order.objects.create(event=event, status='paid', total_amount=amount, platform_commission=amount*.05,
                buyer_name='Fixture', buyer_phone='254700000099')
        response = self.client.get(reverse('accounts:seller_home'), {'q':'no match'})
        self.assertEqual(len(response.context['events']), 0)
        self.assertEqual(response.context['sales']['organizer_share'], Decimal('950'))
        self.assertEqual(response.context['event_count'], 1)

    def test_invalid_new_ticket_keeps_data_and_inline_errors_without_creating_ticket(self):
        response = self.client.post(reverse('accounts:seller_tier', args=[self.event.pk]), {
            'name':'Private lounge', 'description':'Keep this description', 'price':'-10',
            'quantity_total':'20', 'max_per_order':'8', 'is_active':'on'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['tier_form']['name'].value(), 'Private lounge')
        self.assertIn('price', response.context['tier_form'].errors)
        self.assertContains(response, 'Keep this description')
        self.assertContains(response, f'action="{reverse("accounts:seller_edit", args=[self.event.pk])}"')
        self.assertFalse(self.event.ticket_types.exists())

    def test_invalid_existing_ticket_preserves_capacity_and_opens_only_its_form(self):
        tier = TicketType.objects.create(event=self.event, name='VIP', price=2000, quantity_total=10, quantity_sold=6)
        response = self.client.post(reverse('accounts:seller_tier_edit', args=[self.event.pk, tier.pk]), {
            'name':'Updated VIP', 'price':'2500', 'quantity_total':'3','max_per_order':'8','is_active':'on'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['tier_rows'][0]['invalid'])
        self.assertIn('quantity_total', response.context['tier_rows'][0]['form'].errors)
        tier.refresh_from_db()
        self.assertEqual(tier.quantity_total, 10)
        self.assertEqual(tier.name, 'VIP')

    def draft_data(self):
        return {'title':'Theme test', 'category':'concert', 'description':'Live music', 'organizer_name':'Studio A',
                'venue':'Hall', 'city':'Nairobi',
                'start_at':timezone.localtime(timezone.now()+timedelta(days=7)).strftime('%Y-%m-%dT%H:%M')}

    def test_theme_is_saved_and_validated_without_bypassing_publication(self):
        data = self.draft_data()
        data['theme'] = 'coastal'
        response = self.client.post(reverse('accounts:seller_create'), data)
        event = Event.objects.get(title='Theme test')
        self.assertEqual(event.theme, 'coastal')
        self.assertFalse(event.is_published)
        self.assertTrue(response.url.endswith('#tickets'))
        self.assertContains(self.client.get(reverse('accounts:seller_preview', args=[event.pk])), 'theme-coastal')
        data['theme'] = '<script>'
        response = self.client.post(reverse('accounts:seller_edit', args=[event.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('theme', response.context['form'].errors)
        event.refresh_from_db()
        self.assertEqual(event.theme, 'coastal')

    def test_readiness_matches_submission_and_uses_saved_details_after_error(self):
        self.assertEqual(self.client.get(reverse('accounts:seller_edit', args=[self.event.pk])).context['ready_count'], 2)
        TicketType.objects.create(event=self.event, name='Regular', price=1000, quantity_total=20)
        self.assertEqual(self.client.get(reverse('accounts:seller_edit', args=[self.event.pk])).context['ready_count'], 3)
        bad = self.draft_data()
        bad.update({'title':'', 'cover_image-clear':'on'})
        response = self.client.post(reverse('accounts:seller_edit', args=[self.event.pk]), bad)
        self.assertEqual(response.context['ready_count'], 3)
        self.client.post(reverse('accounts:seller_submit', args=[self.event.pk]))
        self.event.refresh_from_db()
        self.assertEqual(self.event.review_status, 'pending')
        self.assertEqual(self.client.post(reverse('accounts:seller_edit', args=[self.event.pk]), self.draft_data()).status_code, 403)

    def test_every_theme_renders_publicly_only_after_publication(self):
        for theme in Event.Theme.values:
            self.event.theme = theme
            self.event.review_status = 'approved'
            self.event.is_published = True
            self.event.save()
            response = self.client.get(self.event.get_absolute_url())
            self.assertContains(response, f'event-theme theme-{theme}')
