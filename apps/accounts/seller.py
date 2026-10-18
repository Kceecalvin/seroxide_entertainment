from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
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
    all_events = request.user.seller_events.all()
    events = all_events.order_by('-created_at')
    query = request.GET.get('q', '').strip()[:200]
    status = request.GET.get('status', '')
    filters = {
        'draft': Q(review_status__in=['draft', 'changes']),
        'pending': Q(review_status='pending'),
        'live': Q(is_published=True, review_status='approved', start_at__gt=timezone.now()),
        'past': Q(start_at__lte=timezone.now()),
    }
    if query:
        events = events.filter(Q(title__icontains=query) | Q(city__icontains=query) | Q(venue__icontains=query))
    if status in filters:
        events = events.filter(filters[status])
    else:
        status = ''
    page = Paginator(events, 12).get_page(request.GET.get('page'))
    sales = Order.objects.filter(event__owner=request.user, status=OrderStatus.PAID).aggregate(gross=Sum('total_amount'), fees=Sum('service_fee'), commission=Sum('platform_commission'), count=Count('id'))
    sales['tickets'] = (sales['gross'] or Decimal(0)) - (sales['fees'] or Decimal(0))
    sales['commission'] = sales['commission'] or Decimal(0)
    sales['organizer_share'] = sales['tickets'] - sales['commission']
    return render(request, 'seller/home.html', {
        'events': page, 'sales': sales, 'event_count': all_events.count(),
        'query': query, 'selected_status': status,
        'status_options': [('', 'All events'), ('draft', 'Needs your attention'),
                           ('pending', 'In review'), ('live', 'Live & upcoming'), ('past', 'Started / past')],
    })


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
            return redirect(reverse('accounts:seller_edit', args=[event.pk]) + ('#tickets' if pk is None else ''))
    return render_editor(request, event, form=form)


@seller_required
@require_POST
@transaction.atomic
def save_tier(request, pk, tier_id=None):
    event = get_object_or_404(Event.objects.select_for_update(), pk=pk, owner=request.user)
    if event.review_status not in ('draft', 'changes'):
        raise PermissionDenied
    tier = get_object_or_404(TicketType.objects.select_for_update(), pk=tier_id, event=event) if tier_id else None
    form = TicketTypeForm(request.POST, instance=tier, auto_id=f'tier_{tier_id or "new"}_%s')
    if form.is_valid():
        tier = form.save(commit=False)
        tier.event = event
        tier.save()
        messages.success(request, 'Ticket tier saved.')
    else:
        return render_editor(request, event, invalid_tier_form=form, invalid_tier_id=tier_id)
    return redirect(reverse('accounts:seller_edit', args=[pk]) + '#tickets')


def publication_checks(event):
    return [
        {'label': 'Future event date', 'done': bool(event and event.start_at > timezone.now()),
         'error': 'Choose a future event date.', 'anchor': 'event-details'},
        {'label': 'Cover image', 'done': bool(event and event.cover_image),
         'error': 'Upload a cover image.', 'anchor': 'event-details'},
        {'label': 'Active paid ticket with capacity',
         'done': bool(event and event.ticket_types.filter(is_active=True, price__gt=0, quantity_total__gt=0).exists()),
         'error': 'Add an active paid ticket tier with capacity.', 'anchor': 'tickets'},
    ]


def publication_errors(event):
    return [check['error'] for check in publication_checks(event) if not check['done']]


def render_editor(request, event, form=None, invalid_tier_form=None, invalid_tier_id=None):
    saved_event = Event.objects.get(pk=event.pk) if event and event.pk else None
    checks = publication_checks(saved_event)
    tiers = list(event.ticket_types.all()) if event else []
    tier_rows = [{
        'tier': tier,
        'form': invalid_tier_form if invalid_tier_form is not None and tier.pk == invalid_tier_id
                else TicketTypeForm(instance=tier, auto_id=f'tier_{tier.pk}_%s'),
        'invalid': invalid_tier_form is not None and tier.pk == invalid_tier_id,
    } for tier in tiers]
    return render(request, 'seller/editor.html', {
        'form': form if form is not None else SellerEventForm(instance=event),
        'event': event, 'editable': not event or event.review_status in ('draft', 'changes'),
        'tier_rows': tier_rows,
        'tier_form': invalid_tier_form if invalid_tier_form is not None and invalid_tier_id is None
                     else TicketTypeForm(auto_id='tier_new_%s', initial={'name': 'Regular'}),
        'ticket_errors': invalid_tier_form is not None,
        'theme_options': [
            ('classic', 'SeroTix signature', 'Blue, red & gold. The original.'),
            ('after-dark', 'After Dark', 'Crimson accents. Late-night energy.'),
            ('coastal', 'Coastal', 'Sea-glass teal. Open-air days.'),
            ('gold-night', 'Gold Night', 'Warm gold. Dinners & special occasions.'),
            ('electric', 'Electric', 'Ice blue. Bold stages & big ideas.'),
        ],
        'checks': checks, 'ready_count': sum(check['done'] for check in checks),
    })


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
