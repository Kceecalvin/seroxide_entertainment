from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from apps.accounts.permissions import scanner_required, can_scan, is_admin, gate_assignments, can_supervise
from .access import grant_order, require_order_access
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from apps.core.ratelimit import ratelimit
from apps.events.models import Event
from apps.payments.services import initiate_paystack_payment, initiate_payment
from django.conf import settings
from apps.payments.availability import available_methods

from .forms import CheckoutForm, MyTicketsLookupForm, WaitlistForm
from .models import Order, OrderStatus, Ticket, TicketStatus, TicketType, WaitlistEntry
from .services import OrderError, create_order


@require_POST
@ratelimit(key_prefix='checkout', limit=20, window_seconds=300)
def checkout(request, slug):
    event = get_object_or_404(Event, slug=slug, is_published=True)
    form = CheckoutForm(request.POST)
    methods = available_methods()
    if not methods or request.POST.get('payment_method', 'mpesa') not in methods:
        messages.error(request, 'Online booking is not available right now. Please contact the team.')
        return redirect(event.get_absolute_url())

    cart = {}
    for key, value in request.POST.items():
        if key.startswith('qty_') and value.strip():
            try:
                qty = int(value)
            except ValueError:
                continue
            if qty > 0:
                cart[key.removeprefix('qty_')] = qty

    if not form.is_valid():
        for errors in form.errors.values():
            for err in errors:
                messages.error(request, err)
        return redirect(event.get_absolute_url())

    if not request.user.is_authenticated and not form.cleaned_data.get('terms_accepted'):
        messages.error(request, 'You need to accept the Terms of Service and Privacy Policy to continue.')
        return redirect(event.get_absolute_url())

    try:
        order = create_order(
            event=event,
            buyer_name=form.cleaned_data['buyer_name'],
            buyer_email=form.cleaned_data['buyer_email'],
            buyer_phone=form.cleaned_data['buyer_phone'],
            cart=cart,
            buyer=request.user,
        )
    except OrderError as exc:
        messages.error(request, str(exc))
        return redirect(event.get_absolute_url())

    grant_order(request, order)

    payment_method = form.cleaned_data['payment_method']

    if payment_method == 'paystack':
        pending_url = request.build_absolute_uri(reverse('tickets:order_pending', args=[order.reference]))
        _, redirect_url = initiate_paystack_payment(order, callback_url=pending_url)
        if not redirect_url:
            messages.error(request, 'Card payment could not be started — please try again or pay with M-Pesa.')
            return redirect(event.get_absolute_url())
        return redirect(redirect_url)

    initiate_payment(order, phone_number=form.cleaned_data['buyer_phone'])
    return redirect('tickets:order_pending', reference=order.reference)


@require_POST
@ratelimit(key_prefix='join-waitlist', limit=10, window_seconds=600)
def join_waitlist(request, ticket_type_id):
    ticket_type = get_object_or_404(TicketType, pk=ticket_type_id, is_active=True, event__is_published=True)
    form = WaitlistForm(request.POST)
    if form.is_valid():
        WaitlistEntry.objects.create(
            ticket_type=ticket_type,
            name=form.cleaned_data['name'],
            email=form.cleaned_data['email'],
            phone=form.cleaned_data['phone'],
        )
        messages.success(request, f"You're on the waitlist for {ticket_type.name} — we'll email you the moment a spot opens up.")
    else:
        for errors in form.errors.values():
            for err in errors:
                messages.error(request, err)
    return redirect(ticket_type.event.get_absolute_url())


@never_cache
@ratelimit(key_prefix='order-lookup', limit=30, window_seconds=300, key_kwarg='reference')
def order_pending(request, reference):
    order = get_object_or_404(Order, reference=reference)
    require_order_access(request, order)
    if order.status == OrderStatus.PAID:
        return redirect('tickets:order_success', reference=order.reference)
    payment = order.payments.order_by('-created_at').first()
    return render(request, 'tickets/order_pending.html', {'order': order, 'payment': payment})


@never_cache
@ratelimit(key_prefix='order-lookup', limit=30, window_seconds=300, key_kwarg='reference')
def order_success(request, reference):
    order = get_object_or_404(Order.objects.prefetch_related('items__tickets', 'items__ticket_type'), reference=reference)
    require_order_access(request, order)
    if order.status != OrderStatus.PAID:
        return redirect('tickets:order_pending', reference=order.reference)
    tickets = Ticket.objects.filter(order_item__order=order).select_related('order_item__ticket_type')
    return render(request, 'tickets/order_success.html', {'order': order, 'tickets': tickets})


@ratelimit(key_prefix='my-tickets-lookup', limit=15, window_seconds=300)
def my_tickets(request):
    form = MyTicketsLookupForm(request.GET or None)
    order = None
    error = None
    if request.GET and form.is_valid():
        try:
            order = Order.objects.get(
                reference__iexact=form.cleaned_data['reference'].strip(),
                buyer_phone__endswith=form.cleaned_data['buyer_phone'].strip()[-9:],
            )
            grant_order(request, order)
        except Order.DoesNotExist:
            error = "We couldn't find an order matching those details."
    return render(request, 'tickets/my_tickets.html', {'form': form, 'order': order, 'error': error})


@never_cache
@scanner_required
def verify_ticket(request, serial):
    event_id = request.session.get('gate_event_id')
    if not event_id:
        messages.info(request, 'Choose the event you are working at, then scan the ticket again.')
        return redirect('tickets:scanner')
    if not can_scan(request.user, event_id):
        raise PermissionDenied('Your gate access has ended.')
    ticket = get_object_or_404(Ticket.objects.select_related('order_item__ticket_type', 'order_item__order__event'),
                              serial=serial, order_item__order__event_id=event_id)
    if request.method == 'POST':
        from .gates import scan_for_event
        body, status = scan_for_event(request.user, event_id, serial)
        if status == 403:
            raise PermissionDenied('Your gate access has ended.')
        messages.success(request, 'Ticket checked in.') if body['ok'] else messages.warning(request, 'Entry denied: ' + body['result'].replace('_', ' ') + '.')
        ticket.refresh_from_db()
    return render(request, 'tickets/verify.html', {'ticket': ticket})


@never_cache
@scanner_required
def scanner(request):
    assignments = gate_assignments(request.user).select_related('event').order_by('starts_at')
    assigned_ids = assignments.values_list('event_id', flat=True)
    from django.db.models import Q
    events = Event.objects.all() if is_admin(request.user) else Event.objects.filter(Q(owner=request.user) | Q(pk__in=assigned_ids))
    page = Paginator(events.order_by('-start_at'), 20).get_page(request.GET.get('page'))
    by_event = {a.event_id: a for a in assignments}
    rows = [{'event': e, 'assignment': by_event.get(e.pk), 'can_scan': can_scan(request.user, e.pk),
             'can_supervise': can_supervise(request.user, e)} for e in page]
    return render(request, 'gates/events.html', {'rows': rows, 'page': page})


@never_cache
@scanner_required
def scanner_event(request, event_id):
    if not can_scan(request.user, event_id):
        raise PermissionDenied('Your gate access is not active.')
    if request.session.get('gate_event_id') != event_id:
        return redirect('tickets:scanner')
    event = get_object_or_404(Event, pk=event_id)
    assignment = gate_assignments(request.user, active=True).filter(event=event).first()
    return render(request, 'tickets/scanner.html', {'event': event, 'assignment': assignment,
                                                  'can_supervise': can_supervise(request.user, event)})


@login_required(login_url='accounts:login')
@require_POST
def scanner_check(request, serial):
    from .gates import scan_for_event
    try:
        event_id = int(request.POST.get('event_id', ''))
        if event_id <= 0 or event_id > 9223372036854775807:
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'result': 'select_event'}, status=400)
    body, status = scan_for_event(request.user, event_id, serial)
    return JsonResponse(body, status=status)
