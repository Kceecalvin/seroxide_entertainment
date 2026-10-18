from django.contrib import messages
from django.contrib.auth.views import LoginView
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core.decorators import superuser_required
from apps.accounts.permissions import admin_required, role_for
from apps.events.models import Event, EventImage, LineupItem
from apps.payments.models import Payment, PaymentStatus
from apps.payments.refunds import RefundError, issue_refund
from apps.tickets.models import Order, OrderItem, OrderStatus, TicketType

from .forms import EventForm, EventImageForm, LineupItemForm, TicketTypeForm


class RoleAwareLoginView(LoginView):
    """Same login form for every staff account — gatemen and full admins
    alike — but lands each on the page they actually have access to, so a
    gateman (is_staff only) isn't bounced into the now-restricted dashboard
    and back out again in a loop."""
    template_name = 'dashboard/login.html'
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        if role_for(self.request.user) in ('admin', 'superadmin'):
            return reverse('dashboard:home')
        if role_for(self.request.user) == 'scanner':
            return reverse('tickets:scanner')
        if role_for(self.request.user) == 'seller':
            return reverse('accounts:seller_home')
        return reverse('accounts:my_account')


@admin_required
def dashboard_home(request):
    events = Event.objects.all().prefetch_related('ticket_types').order_by('-start_at')
    # Reservations are not sales, and current tier prices can differ from the
    # amount a buyer actually paid. Report immutable paid-order amounts.
    paid_orders = Order.objects.filter(status=OrderStatus.PAID)
    per_event = {
        row['event_id']: row for row in paid_orders.values('event_id').annotate(
            gross=Sum('total_amount'), fees=Sum('service_fee'), commission=Sum('platform_commission'), orders=Count('id'),
        )
    }
    paid_quantities = {
        row['order__event_id']: row['quantity'] for row in
        OrderItem.objects.filter(order__status=OrderStatus.PAID)
        .values('order__event_id').annotate(quantity=Sum('quantity'))
    }
    totals = paid_orders.aggregate(gross=Sum('total_amount'), fees=Sum('service_fee'), commission=Sum('platform_commission'), orders=Count('id'))
    gross = totals['gross'] or Decimal('0')
    fees = totals['fees'] or Decimal('0')
    commission = totals['commission'] or Decimal('0')
    order_count = totals['orders']
    metrics = {
        'ticket_sales': gross - fees,
        'platform_fees': fees + commission,
        'organizer_share': gross - fees - commission,
        'paid_orders': order_count,
        'average_order': gross / order_count if order_count else Decimal('0'),
        'pending_orders': Order.objects.filter(status=OrderStatus.PENDING).count(),
    }
    rows = []
    for event in events:
        types = list(event.ticket_types.all())
        sales = per_event.get(event.pk, {})
        rows.append({
            'event': event,
            'sold': paid_quantities.get(event.pk, 0),
            'capacity': sum(t.quantity_total for t in types),
            'revenue': sales.get('gross', 0) - sales.get('fees', 0),
            'fees': sales.get('fees', 0) + sales.get('commission', 0),
            'organizer_share': sales.get('gross', 0) - sales.get('fees', 0) - sales.get('commission', 0),
        })
    return render(request, 'dashboard/event_list.html', {'rows': rows, 'metrics': metrics})


@admin_required
def event_create(request):
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save()
            messages.success(request, f'"{event.title}" created. Now add ticket types and pricing below.')
            return redirect('dashboard:event_edit', slug=event.slug)
    else:
        form = EventForm(initial={'start_at': timezone.now()})
    return render(request, 'dashboard/event_form.html', {'form': form, 'event': None})


@admin_required
def event_edit(request, slug):
    event = get_object_or_404(Event, slug=slug)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, 'Event details saved.')
            return redirect('dashboard:event_edit', slug=event.slug)
    else:
        form = EventForm(instance=event)

    return render(request, 'dashboard/event_form.html', {
        'form': form,
        'event': event,
        'ticket_types': (
            event.ticket_types.annotate(
                waitlist_count=Count('waitlist_entries', filter=Q(waitlist_entries__notified_at__isnull=True))
            )
            if event else []
        ),
        'new_ticket_form': TicketTypeForm(),
        'gallery': event.gallery.all() if event else [],
        'new_image_form': EventImageForm(),
        'lineup': event.lineup.all() if event else [],
        'new_lineup_form': LineupItemForm(),
    })


@admin_required
def ticket_type_create(request, slug):
    event = get_object_or_404(Event, slug=slug)
    form = TicketTypeForm(request.POST)
    if form.is_valid():
        ticket_type = form.save(commit=False)
        ticket_type.event = event
        ticket_type.save()
        messages.success(request, f'Ticket type "{ticket_type.name}" added.')
    else:
        messages.error(request, 'Could not add that ticket type — ' + '; '.join(
            f'{field}: {", ".join(errs)}' for field, errs in form.errors.items()
        ))
    return redirect('dashboard:event_edit', slug=event.slug)


@admin_required
def ticket_type_edit(request, pk):
    ticket_type = get_object_or_404(TicketType, pk=pk)
    if request.method == 'POST':
        form = TicketTypeForm(request.POST, instance=ticket_type)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ticket type updated.')
            return redirect('dashboard:event_edit', slug=ticket_type.event.slug)
    else:
        form = TicketTypeForm(instance=ticket_type)
    return render(request, 'dashboard/ticket_type_form.html', {'form': form, 'ticket_type': ticket_type})


@admin_required
def ticket_type_toggle(request, pk):
    if request.method != 'POST':
        return redirect('dashboard:home')
    ticket_type = get_object_or_404(TicketType, pk=pk)
    ticket_type.is_active = not ticket_type.is_active
    ticket_type.save(update_fields=['is_active'])
    messages.success(
        request,
        f'"{ticket_type.name}" is now {"on sale" if ticket_type.is_active else "off sale"}.',
    )
    return redirect('dashboard:event_edit', slug=ticket_type.event.slug)


@admin_required
def event_image_create(request, slug):
    event = get_object_or_404(Event, slug=slug)
    form = EventImageForm(request.POST, request.FILES)
    if form.is_valid():
        image = form.save(commit=False)
        image.event = event
        image.order = event.gallery.count()
        image.save()
        messages.success(request, 'Photo added to the gallery.')
    else:
        messages.error(request, 'Could not add that photo — check the file and try again.')
    return redirect('dashboard:event_edit', slug=event.slug)


@admin_required
def event_image_delete(request, pk):
    if request.method != 'POST':
        return redirect('dashboard:home')
    image = get_object_or_404(EventImage, pk=pk)
    slug = image.event.slug
    image.delete()
    messages.success(request, 'Photo removed.')
    return redirect('dashboard:event_edit', slug=slug)


@admin_required
def lineup_item_create(request, slug):
    event = get_object_or_404(Event, slug=slug)
    form = LineupItemForm(request.POST, request.FILES)
    if form.is_valid():
        item = form.save(commit=False)
        item.event = event
        item.order = event.lineup.count()
        item.save()
        messages.success(request, f'"{item.name}" added to the lineup.')
    else:
        messages.error(request, 'Could not add that lineup item — check the fields and try again.')
    return redirect('dashboard:event_edit', slug=event.slug)


@admin_required
def lineup_item_delete(request, pk):
    if request.method != 'POST':
        return redirect('dashboard:home')
    item = get_object_or_404(LineupItem, pk=pk)
    slug = item.event.slug
    item.delete()
    messages.success(request, 'Removed from the lineup.')
    return redirect('dashboard:event_edit', slug=slug)


@admin_required
def event_orders(request, slug):
    event = get_object_or_404(Event, slug=slug)
    orders = (
        Order.objects.filter(event=event)
        .exclude(status=OrderStatus.PENDING)
        .prefetch_related('items__ticket_type', 'payments')
        .order_by('-created_at')
    )
    rows = []
    for order in orders:
        payments = list(order.payments.all())
        # The payment actually worth showing/refunding: prefer completed or
        # already-refunded over a stray failed/pending attempt on the same order.
        payment = next(
            (p for p in payments if p.status in (PaymentStatus.COMPLETED, PaymentStatus.REFUNDED)),
            payments[0] if payments else None,
        )
        rows.append({'order': order, 'payment': payment})
    return render(request, 'dashboard/event_orders.html', {'event': event, 'rows': rows})


@superuser_required
def issue_refund_view(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        try:
            issue_refund(payment, manual_reference=request.POST.get('manual_reference', ''))
            messages.success(
                request,
                f'Refund recorded for order {payment.order.reference} — order cancelled, tickets voided, stock released.',
            )
        except RefundError as exc:
            messages.error(request, str(exc))
    return redirect('dashboard:event_orders', slug=payment.order.event.slug)


@superuser_required
def payment_reconciliation(request):
    """Payments where money was confirmed received but fulfilment never
    produced a ticket — see apps/payments/management/commands/find_orphaned_payments.py
    for why this can happen at all. Should normally be empty."""
    orphaned = (
        Payment.objects.filter(status=PaymentStatus.COMPLETED)
        .exclude(order__status=OrderStatus.PAID)
        .select_related('order', 'order__event')
        .order_by('-created_at')
    )
    return render(request, 'dashboard/payment_reconciliation.html', {'orphaned': orphaned})


@superuser_required
def payment_retry_fulfillment(request, pk):
    if request.method != 'POST':
        return redirect('dashboard:payment_reconciliation')
    payment = get_object_or_404(Payment, pk=pk, status=PaymentStatus.COMPLETED)
    from apps.tickets.services import fulfill_order
    try:
        fulfill_order(payment.order)
        messages.success(request, f'Order {payment.order.reference} fulfilled — tickets minted.')
    except Exception as exc:
        messages.error(request, f'Still failing for {payment.order.reference}: {exc}')
    return redirect('dashboard:payment_reconciliation')
