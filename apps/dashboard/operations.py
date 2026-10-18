from django import forms
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from apps.accounts.models import AccountProfile, GateAssignment, AccessAudit
from apps.accounts.permissions import admin_required, role_for
from apps.accounts.seller import publication_errors
from apps.core.decorators import superuser_required
from apps.core.mailer import notify, deliver
from apps.core.models import EmailDelivery
from apps.events.models import Event, EventReview

User = get_user_model()


class AccessForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.filter(is_superuser=False).order_by('username'))
    role = forms.ChoiceField(choices=AccountProfile.Role.choices)
    events = forms.ModelMultipleChoiceField(queryset=Event.objects.all(), required=False, widget=forms.CheckboxSelectMultiple, help_text='Scanner grants use an event-time shift (up to 24 hours). Use the event Gate team page for custom shifts and supervisors.')


@superuser_required
@transaction.atomic
def team(request):
    form = AccessForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = User.objects.select_for_update(no_key=True).get(pk=form.cleaned_data['user'].pk)
        if user.is_superuser or user.pk == request.user.pk:
            raise PermissionDenied
        profile, _ = AccountProfile.objects.get_or_create(user=user)
        before = profile.role
        profile.role = form.cleaned_data['role']
        profile.save()
        # These application roles never receive Django-admin privileges.
        user.is_staff = False
        user.save(update_fields=['is_staff'])
        GateAssignment.objects.filter(user=user).delete()
        if profile.role == 'scanner':
            GateAssignment.objects.bulk_create([GateAssignment(user=user, event=e, created_by=request.user,
                starts_at=e.start_at-timedelta(hours=2), ends_at=e.start_at+timedelta(hours=12))
                for e in form.cleaned_data['events']])
        AccessAudit.objects.create(actor=request.user, subject=user, detail=f'{before} → {profile.role}; events: {list(form.cleaned_data["events"].values_list("pk", flat=True))}')
        messages.success(request, 'Access updated. Scanner assignments take effect immediately.')
        return redirect('dashboard:team')
    users = User.objects.filter(is_active=True).select_related('account_profile').prefetch_related('gate_assignments__event').order_by('username')
    rows = [{'user': u, 'role': role_for(u)} for u in users]
    return render(request, 'dashboard/team.html', {'form': form, 'members': rows})


@admin_required
@transaction.atomic
def review(request, pk):
    event = get_object_or_404(Event.objects.select_for_update().select_related('owner'), pk=pk, owner__isnull=False)
    if request.method == 'POST':
        action = request.POST.get('decision')
        note = request.POST.get('note', '').strip()[:2000]
        if event.owner_id == request.user.pk:
            raise PermissionDenied('An organizer cannot review their own event.')
        if event.review_status != 'pending':
            messages.error(request, 'Only submitted events can be reviewed.')
        elif action not in ('approved', 'changes'):
            messages.error(request, 'Choose approve or request changes.')
        elif action == 'changes' and not note:
            messages.error(request, 'Explain what the seller needs to change.')
        elif action == 'approved' and publication_errors(event):
            messages.error(request, 'This event is not ready: ' + ' '.join(publication_errors(event)))
        else:
            event.review_status = action
            event.review_note = note
            event.is_published = action == 'approved'
            event.reviewed_by = request.user
            event.reviewed_at = timezone.now()
            event.save()
            EventReview.objects.create(event=event, actor=request.user, status=action, note=note)
            heading = 'Your event is live' if action == 'approved' else 'Your event needs a few changes'
            notify(event.owner, heading, f'{event.title}\n\n{note}', reverse('accounts:seller_edit', args=[event.pk]))
            messages.success(request, 'Decision saved and seller notification queued.')
            return redirect('dashboard:reviews')
    return render(request, 'dashboard/review.html', {'event': event})


@admin_required
def reviews(request):
    events = Event.objects.filter(owner__isnull=False, review_status='pending').select_related('owner').order_by('updated_at')
    return render(request, 'dashboard/reviews.html', {'events': events})


@superuser_required
def emails(request):
    deliveries = Paginator(EmailDelivery.objects.order_by('-created_at'), 30).get_page(request.GET.get('page'))
    return render(request, 'dashboard/emails.html', {'deliveries': deliveries})


@superuser_required
@require_POST
def retry_email(request, pk):
    delivery = get_object_or_404(EmailDelivery, pk=pk, status__in=['pending', 'failed'])
    # Exhausted deliveries need an explicit owner retry; sent mail cannot be resent here.
    if delivery.attempts >= 5:
        delivery.attempts = 0
        delivery.save(update_fields=['attempts'])
    succeeded = deliver(pk)
    messages.info(request, 'Email sent.' if succeeded else 'Delivery failed. Check the SMTP configuration.')
    return redirect('dashboard:emails')
