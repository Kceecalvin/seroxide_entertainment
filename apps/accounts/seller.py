from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone
from apps.events.models import Event, EventReview
from apps.tickets.models import Order, OrderStatus, TicketType
from apps.core.mailer import notify
from .models import AccountProfile
from .permissions import seller_required, role_for
from .seller_forms import SellerEventForm, SellerOnboardingForm, TicketTypeForm


@login_required(login_url='accounts:login')
def onboard(request):
    if role_for(request.user) == 'seller':
        return redirect('accounts:seller_home')
    if role_for(request.user) != 'buyer':
        raise PermissionDenied
    form = SellerOnboardingForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            profile, _ = AccountProfile.objects.get_or_create(user=request.user)
            profile.role = 'seller'
            profile.business_name = form.cleaned_data['business_name']
            profile.save()
            notify(request.user, 'Your seller studio is ready', 'Build your first event, add ticket tiers, and submit it for review.', reverse('accounts:seller_home'))
        return redirect('accounts:seller_home')
    return render(request, 'seller/onboard.html', {'form': form})


@seller_required
def home(request):
    events = request.user.seller_events.prefetch_related('ticket_types').order_by('-created_at')
    sales = Order.objects.filter(event__owner=request.user, status=OrderStatus.PAID).aggregate(gross=Sum('total_amount'), fees=Sum('service_fee'), commission=Sum('platform_commission'), count=Count('id'))
    sales['tickets'] = (sales['gross'] or Decimal(0)) - (sales['fees'] or Decimal(0))
    sales['commission'] = sales['commission'] or Decimal(0)
    sales['organizer_share'] = sales['tickets'] - sales['commission']
    return render(request, 'seller/home.html', {'events': events, 'sales': sales})


@seller_required
@transaction.atomic
def edit_event(request, pk=None):
    event = get_object_or_404(Event.objects.select_for_update(), pk=pk, owner=request.user) if pk else None
    editable = not event or event.review_status in ('draft', 'changes')
    form = SellerEventForm(request.POST if request.method == 'POST' else None, request.FILES or None, instance=event,
                           initial={'organizer_name': request.user.account_profile.business_name} if event is None else None)
    if request.method == 'POST':
        if not editable:
            raise PermissionDenied('Withdraw the listing before changing approved or submitted content.')
        if form.is_valid():
            event = form.save(commit=False)
            event.owner = request.user
            event.review_status = 'draft'
            event.is_published = False
            event.is_featured = False
            event.save()
            messages.success(request, 'Draft saved. Your event is private until approved.')
            return redirect('accounts:seller_edit', pk=event.pk)
    return render(request, 'seller/editor.html', {'form': form, 'event': event, 'editable': editable, 'tier_form': TicketTypeForm()})


@seller_required
@require_POST
@transaction.atomic
def save_tier(request, pk, tier_id=None):
    event = get_object_or_404(Event.objects.select_for_update(), pk=pk, owner=request.user)
    if event.review_status not in ('draft', 'changes'):
        raise PermissionDenied
    tier = get_object_or_404(TicketType.objects.select_for_update(), pk=tier_id, event=event) if tier_id else None
    form = TicketTypeForm(request.POST, instance=tier)
    if form.is_valid():
        tier = form.save(commit=False)
        tier.event = event
        tier.save()
        messages.success(request, 'Ticket tier saved.')
    else:
        messages.error(request, '; '.join(f'{k}: {", ".join(v)}' for k, v in form.errors.items()))
    return redirect('accounts:seller_edit', pk=pk)


def publication_errors(event):
    problems = []
    if event.start_at <= timezone.now():
        problems.append('Choose a future event date.')
    if not event.cover_image:
        problems.append('Upload a cover image.')
    if not event.ticket_types.filter(is_active=True, price__gt=0, quantity_total__gt=0).exists():
        problems.append('Add an active paid ticket tier with capacity.')
    return problems


@seller_required
@require_POST
@transaction.atomic
def submit(request, pk):
    event = get_object_or_404(Event.objects.select_for_update(), pk=pk, owner=request.user)
    if event.review_status not in ('draft', 'changes'):
        messages.info(request, 'This event is already submitted or approved.')
    else:
        errors = publication_errors(event)
        if errors:
            for error in errors: messages.error(request, error)
        else:
            event.review_status = 'pending'
            event.review_note = ''
            event.save()
            EventReview.objects.create(event=event, actor=request.user, status='pending')
            notify(request.user, 'Your event is in review', f'{event.title} has been submitted. We will email you when a decision is ready.', reverse('accounts:seller_edit', args=[pk]))
            messages.success(request, 'Submitted. An admin will review your event before it goes live.')
    return redirect('accounts:seller_edit', pk=pk)


@seller_required
@require_POST
@transaction.atomic
def withdraw(request, pk):
    event = get_object_or_404(Event.objects.select_for_update(), pk=pk, owner=request.user)
    event.review_status = 'draft'
    event.is_published = False
    event.save()
    EventReview.objects.create(event=event, actor=request.user, status='draft', note='Seller withdrew listing for editing; existing tickets remain valid.')
    messages.info(request, 'Listing withdrawn from sale. Existing tickets remain valid. Submit again after editing.')
    return redirect('accounts:seller_edit', pk=pk)


@seller_required
def preview(request, pk):
    event = get_object_or_404(Event.objects.prefetch_related('ticket_types'), pk=pk, owner=request.user)
    return render(request, 'seller/preview.html', {'event': event})
