from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.events.models import Event
from apps.tickets.models import TicketType, Ticket, GateScanLog, OrderStatus
from apps.tickets.services import create_order, fulfill_order
from .models import AccountProfile, GateAssignment, GateInvitation
from .permissions import can_scan

User = get_user_model()


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class GateTeamTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user('owner-a', 'owner-a@example.test', 'SafePassword123!')
        self.other = User.objects.create_user('owner-b', 'owner-b@example.test', 'SafePassword123!')
        self.guard = User.objects.create_user('guard', 'guard@example.test', 'SafePassword123!')
        self.stranger = User.objects.create_user('stranger', 'stranger@example.test', 'SafePassword123!')
        for user, role in [(self.owner, 'seller'), (self.other, 'seller'), (self.guard, 'buyer'), (self.stranger, 'buyer')]:
            AccountProfile.objects.create(user=user, role=role)
        self.event = Event.objects.create(owner=self.owner, title='Client A private event', venue='Venue A', start_at=timezone.now()+timedelta(days=2), review_status='approved')
        self.other_event = Event.objects.create(owner=self.other, title='Client B private event', venue='Venue B', start_at=timezone.now()+timedelta(days=2), review_status='approved')
        self.client.force_login(self.owner)

    def invite(self, **overrides):
        now = timezone.now()
        data = {'email': self.guard.email, 'gate_label': 'North entrance',
                'starts_at': (now-timedelta(minutes=5)).isoformat(), 'ends_at': (now+timedelta(hours=6)).isoformat()}
        data.update(overrides)
        with patch('apps.accounts.gates.notify'):
            response = self.client.post(reverse('accounts:gate_team', args=[self.event.pk]), data)
        self.assertEqual(response.status_code, 302)
        return self.client.session['new_gate_invite']['path']

    def grant(self, event=None, **kwargs):
        return GateAssignment.objects.create(user=self.guard, event=event or self.event, **kwargs)

    def guard_client(self):
        client = Client();client.force_login(self.guard);return client

    def ticket(self, event=None):
        event = event or self.event
        tier = TicketType.objects.create(event=event, name='General', price=1000, quantity_total=10)
        order = create_order(event=event, buyer_name='Private attendee', buyer_email='', buyer_phone='254700000001', cart={tier.pk:1})
        fulfill_order(order)
        return Ticket.objects.get(order_item__order=order)

    def scan(self, client, ticket, event=None):
        return client.post(reverse('tickets:scanner_check', args=[ticket.serial]), {'event_id': (event or self.event).pk})

    def test_owner_cannot_view_or_invite_another_clients_team(self):
        url = reverse('accounts:gate_team', args=[self.other_event.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {'email':self.guard.email}).status_code, 403)
        self.assertEqual(GateInvitation.objects.count(), 0)

    def test_invitation_is_personal_single_use_and_does_not_change_global_role(self):
        path = self.invite(is_supervisor='on', role='admin', is_superuser='on')
        stranger = Client();stranger.force_login(self.stranger)
        self.assertEqual(stranger.post(path).status_code, 403)
        client = self.guard_client()
        self.assertEqual(client.get(path).status_code, 200)
        self.assertEqual(client.post(path).status_code, 302)
        self.assertEqual(client.post(path).status_code, 410)
        assignment = self.guard.gate_assignments.get()
        self.assertTrue(assignment.is_supervisor)
        self.guard.refresh_from_db()
        self.assertEqual(self.guard.account_profile.role, 'buyer')
        self.assertFalse(self.guard.is_staff or self.guard.is_superuser)
        self.assertFalse(self.guard.gate_assignments.filter(event=self.other_event).exists())
        self.assertEqual(client.get(reverse('dashboard:home')).status_code, 403)

    def test_anonymous_invitation_preserves_login_destination(self):
        path = self.invite()
        response = Client().get(path)
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response.url)
        self.assertContains(Client().get(response.url), 'next=')

    def test_expired_and_revoked_invitations_cannot_be_accepted(self):
        path = self.invite()
        GateInvitation.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.guard_client().post(path).status_code, 410)
        path = self.invite()
        invitation = GateInvitation.objects.latest('pk')
        self.client.post(reverse('accounts:gate_invite_revoke', args=[self.event.pk, invitation.pk]))
        self.assertEqual(self.guard_client().post(path).status_code, 410)
        self.assertFalse(self.guard.gate_assignments.exists())

    def test_reissued_invitation_invalidates_previous_link(self):
        old = self.invite()
        new = self.invite()
        client = self.guard_client()
        self.assertEqual(client.post(old).status_code, 410)
        self.assertEqual(client.post(new).status_code, 302)

    def test_owner_transfer_invalidates_unaccepted_invitation(self):
        path = self.invite()
        self.event.owner = self.other;self.event.save()
        self.assertEqual(self.guard_client().post(path).status_code, 410)

    def test_shift_validation_and_invitation_does_not_create_fake_accounts(self):
        before = User.objects.count()
        self.invite(email='new-person@example.test')
        self.assertEqual(User.objects.count(), before)
        now = timezone.now()
        response = self.client.post(reverse('accounts:gate_team', args=[self.event.pk]), {
            'email':self.guard.email, 'gate_label':'Main', 'starts_at':now.isoformat(), 'ends_at':(now+timedelta(hours=25)).isoformat()})
        self.assertContains(response, 'up to 24 hours')
        self.assertEqual(GateInvitation.objects.count(), 1)

    def test_future_and_expired_shifts_cannot_scan(self):
        now = timezone.now()
        assignment = self.grant(starts_at=now+timedelta(hours=1), ends_at=now+timedelta(hours=2))
        ticket = self.ticket();client = self.guard_client()
        self.assertContains(client.get(reverse('tickets:scanner')), 'Scanning opens when your shift starts')
        self.assertEqual(self.scan(client, ticket).status_code, 403)
        assignment.starts_at=now-timedelta(hours=2);assignment.ends_at=now-timedelta(hours=1);assignment.save()
        self.assertEqual(self.scan(client, ticket).status_code, 403)
        self.assertFalse(can_scan(self.guard, self.event.pk))
        ticket.refresh_from_db();self.assertEqual(ticket.status, 'valid')

    def test_cross_event_scan_rejected_even_when_guard_assigned_to_both(self):
        self.grant();self.grant(self.other_event)
        ticket = self.ticket(self.other_event)
        response = self.scan(self.guard_client(), ticket)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {'ok':False,'result':'wrong_event'})
        ticket.refresh_from_db();self.assertEqual(ticket.status, 'valid')
        log=GateScanLog.objects.get();self.assertIsNone(log.ticket_id)
        self.assertEqual(log.event_id, self.event.pk)

    def test_missing_event_does_not_admit(self):
        self.grant();ticket=self.ticket()
        self.assertEqual(self.guard_client().post(reverse('tickets:scanner_check',args=[ticket.serial])).status_code,400)
        ticket.refresh_from_db();self.assertEqual(ticket.status,'valid')

    def test_revocation_blocks_existing_login_but_preserves_other_client_access(self):
        assignment=self.grant();self.grant(self.other_event)
        client=self.guard_client();ticket=self.ticket()
        path=self.invite()
        self.client.post(reverse('accounts:gate_revoke',args=[self.event.pk,assignment.pk]))
        self.assertEqual(self.scan(client,ticket).status_code,403)
        self.assertEqual(client.post(path).status_code,410)
        self.assertTrue(can_scan(self.guard,self.other_event.pk))
        self.assertFalse(can_scan(self.guard,self.event.pk))

    def test_cross_client_revoke_is_forbidden(self):
        assignment=self.grant(self.other_event)
        self.assertEqual(self.client.post(reverse('accounts:gate_revoke',args=[self.other_event.pk,assignment.pk])).status_code,403)
        self.assertEqual(self.client.post(reverse('accounts:gate_revoke',args=[self.event.pk,assignment.pk])).status_code,404)
        assignment.refresh_from_db();self.assertIsNone(assignment.revoked_at)

    def test_only_supervisor_and_event_owner_can_read_activity(self):
        assignment=self.grant();client=self.guard_client()
        url=reverse('tickets:gate_supervisor',args=[self.event.pk])
        self.assertEqual(client.get(url).status_code,403)
        assignment.is_supervisor=True;assignment.save()
        self.scan(client,self.ticket())
        response=client.get(url)
        self.assertContains(response,'Admissions by guard')
        self.assertEqual(response.context['admitted'],1)
        self.assertNotContains(response,self.other_event.title)
        self.assertEqual(client.get(reverse('tickets:gate_supervisor',args=[self.other_event.pk])).status_code,403)
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(client.post(reverse('accounts:gate_team',args=[self.event.pk]),{}).status_code,403)
        assignment.revoked_at=timezone.now();assignment.save()
        self.assertEqual(client.get(url).status_code,403)

    def test_duplicate_and_invalid_scans_have_event_scoped_audit(self):
        self.grant();client=self.guard_client();ticket=self.ticket()
        self.assertTrue(self.scan(client,ticket).json()['ok'])
        self.assertEqual(self.scan(client,ticket).json()['result'],'already_used')
        self.assertEqual(client.post(reverse('tickets:scanner_check',args=[uuid4()]),{'event_id':self.event.pk}).status_code,404)
        self.assertCountEqual(list(GateScanLog.objects.values_list('result',flat=True)),['checked_in','already_used','not_found'])
        self.assertTrue(all(log.actor_id==self.guard.pk for log in GateScanLog.objects.all()))

    def test_manual_qr_path_requires_selected_event_and_respects_revocation(self):
        assignment=self.grant();ticket=self.ticket();client=self.guard_client()
        url=reverse('tickets:verify',args=[ticket.serial])
        self.assertRedirects(client.get(url),reverse('tickets:scanner'))
        client.post(reverse('tickets:select_gate_event',args=[self.event.pk]))
        self.assertContains(client.get(url),'Valid ticket')
        self.client.post(reverse('accounts:gate_revoke',args=[self.event.pk,assignment.pk]))
        self.assertEqual(client.post(url).status_code,403)
        ticket.refresh_from_db();self.assertEqual(ticket.status,'valid')

    def test_manual_qr_does_not_offer_admission_for_unpaid_ticket(self):
        self.grant();ticket=self.ticket();client=self.guard_client()
        client.post(reverse('tickets:select_gate_event',args=[self.event.pk]))
        ticket.order.status=OrderStatus.CANCELLED;ticket.order.save()
        response=client.get(reverse('tickets:verify',args=[ticket.serial]))
        self.assertContains(response,'Payment not confirmed')
        self.assertNotContains(response,'Valid ticket')

    def test_mutations_require_csrf_and_get_cannot_revoke(self):
        assignment=self.grant()
        url=reverse('accounts:gate_revoke',args=[self.event.pk,assignment.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        client=Client(enforce_csrf_checks=True);client.force_login(self.owner)
        self.assertEqual(client.post(url).status_code,403)

    def test_signup_invitation_destination_cannot_redirect_offsite(self):
        response=Client().get(reverse('accounts:signup')+'?next=https://evil.example/')
        self.assertEqual(response.context['next'],'')
        response=Client().get(reverse('accounts:signup')+'?next=/account/gate-invites/test/')
        self.assertEqual(response.context['next'],'/account/gate-invites/test/')
