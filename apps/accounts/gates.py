"""Event-scoped gate invitations. These grants never change global account roles."""
import hashlib
import secrets
from datetime import timedelta
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from apps.core.mailer import notify
from apps.core.ratelimit import ratelimit
from apps.events.models import Event
from .models import AccessAudit, GateAssignment, GateInvitation
from .permissions import can_manage_gate


class GateInviteForm(forms.Form):
    email = forms.EmailField(label='Guard’s account email')
    gate_label = forms.CharField(max_length=80, initial='Main gate', label='Gate / entrance')
    starts_at = forms.DateTimeField(label='Shift starts (Nairobi time)', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    ends_at = forms.DateTimeField(label='Shift ends (Nairobi time)', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    is_supervisor = forms.BooleanField(required=False, label='Gate supervisor — can view this event’s admission activity')

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean(self):
        data = super().clean()
        start, end = data.get('starts_at'), data.get('ends_at')
        if start and end:
            if end <= start or end <= timezone.now():
                self.add_error('ends_at', 'Choose a future end after the start of the shift.')
            elif end - start > timedelta(hours=24):
                self.add_error('ends_at', 'A shift can last up to 24 hours. Schedule the next shift separately.')
        return data


def managed_event(request, pk, *, lock=False):
    query = Event.objects.select_for_update() if lock else Event.objects.all()
    event = get_object_or_404(query, pk=pk)
    if not can_manage_gate(request.user, event):
        raise PermissionDenied
    return event


@never_cache
@login_required(login_url='accounts:login')
@ratelimit(key_prefix='gate-invites', limit=120, window_seconds=3600, key_kwarg='pk')
@transaction.atomic
def team(request, pk):
    event = managed_event(request, pk, lock=request.method == 'POST')
    start = max(timezone.now(), event.start_at - timedelta(hours=2))
    form = GateInviteForm(request.POST or None, initial={'starts_at': start, 'ends_at': start + timedelta(hours=12)})
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        # Reissuing revokes older unaccepted invitations, not the person's existing shift.
        GateInvitation.objects.filter(event=event, email__iexact=data['email'], accepted_at__isnull=True, revoked_at__isnull=True).update(revoked_at=timezone.now())
        token = secrets.token_urlsafe(32)
        invitation = GateInvitation.objects.create(event=event, created_by=request.user,
            token_digest=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=min(data['ends_at'], timezone.now()+timedelta(days=7)), **data)
        path = reverse('accounts:gate_accept', args=[token])
        notify(data['email'], f'Gate team invitation: {event.title}',
               f'You are invited to work at {data["gate_label"]}. Sign in with this email address to review and accept your shift. This invitation expires within seven days; gate access ends automatically at the scheduled time.', path)
        request.session['new_gate_invite'] = {'event_id': event.pk, 'path': path}
        AccessAudit.objects.create(actor=request.user, detail=f'Gate invitation {invitation.pk} created for event {event.pk}; supervisor={data["is_supervisor"]}')
        messages.success(request, 'Invitation created and email queued. You can also copy the personal invitation link below.')
        return redirect('accounts:gate_team', pk=event.pk)
    recent = request.session.get('new_gate_invite', {})
    invitation_url = ''
    if recent.get('event_id') == event.pk:
        request.session.pop('new_gate_invite', None)
        invitation_url = request.build_absolute_uri(recent['path'])
    members = event.gate_assignments.select_related('user').order_by('-ends_at')
    invitations = event.gate_invitations.filter(accepted_at__isnull=True).order_by('-created_at')
    return render(request, 'gates/team.html', {'event': event, 'form': form,
        'members': Paginator(members, 30).get_page(request.GET.get('members')),
        'invitations': Paginator(invitations, 20).get_page(request.GET.get('invitations')),
        'invitation_url': invitation_url})


@never_cache
@login_required(login_url='accounts:login')
@require_POST
@transaction.atomic
def revoke(request, pk, assignment_id):
    event = managed_event(request, pk, lock=True)
    assignment = get_object_or_404(GateAssignment.objects.select_for_update(), pk=assignment_id, event=event)
    assignment.revoked_at = timezone.now()
    assignment.save(update_fields=['revoked_at'])
    # A pending invitation must not silently restore a revoked guard's access.
    GateInvitation.objects.filter(event=event, email__iexact=assignment.user.email,
        accepted_at__isnull=True, revoked_at__isnull=True).update(revoked_at=timezone.now())
    AccessAudit.objects.create(actor=request.user, subject=assignment.user, detail=f'Gate access revoked for event {event.pk}')
    messages.success(request, 'Gate access revoked. Further scans for this event are blocked, including on a phone already signed in.')
    return redirect('accounts:gate_team', pk=event.pk)


@never_cache
@login_required(login_url='accounts:login')
@require_POST
@transaction.atomic
def revoke_invite(request, pk, invitation_id):
    event = managed_event(request, pk, lock=True)
    invitation = get_object_or_404(GateInvitation, event=event, pk=invitation_id, accepted_at__isnull=True)
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=['revoked_at'])
    AccessAudit.objects.create(actor=request.user, detail=f'Gate invitation {invitation.pk} revoked for event {event.pk}')
    messages.success(request, 'Invitation revoked.')
    return redirect('accounts:gate_team', pk=event.pk)


@never_cache
@login_required(login_url='accounts:login')
@transaction.atomic
def accept(request, token):
    invitation = get_object_or_404(GateInvitation, token_digest=hashlib.sha256(token.encode()).hexdigest())
    # Same event-first lock order as revoke and admission, preventing a revoke/accept race.
    Event.objects.select_for_update().get(pk=invitation.event_id)
    invitation = GateInvitation.objects.select_for_update().select_related('event', 'created_by').get(pk=invitation.pk)
    if invitation.revoked_at or invitation.accepted_at or invitation.expires_at <= timezone.now() or not can_manage_gate(invitation.created_by, invitation.event):
        return render(request, 'gates/invitation_unavailable.html', status=410)
    if not request.user.is_active or request.user.email.casefold() != invitation.email.casefold():
        return render(request, 'gates/invitation_mismatch.html', status=403)
    if request.method == 'POST':
        GateAssignment.objects.update_or_create(user=request.user, event=invitation.event, defaults={
            'starts_at': invitation.starts_at, 'ends_at': invitation.ends_at,
            'gate_label': invitation.gate_label, 'is_supervisor': invitation.is_supervisor,
            'revoked_at': None, 'created_by': invitation.created_by})
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=['accepted_at'])
        AccessAudit.objects.create(actor=request.user, subject=request.user, detail=f'Gate invitation {invitation.pk} accepted for event {invitation.event_id}')
        messages.success(request, 'Shift accepted. Choose your event when your shift starts.')
        return redirect('tickets:scanner')
    response = render(request, 'gates/accept.html', {'invitation': invitation})
    # Keep the private token out of Referer URLs without suppressing the
    # same-origin POST Origin that Django's CSRF protection requires.
    response['Referrer-Policy'] = 'strict-origin'
    return response
