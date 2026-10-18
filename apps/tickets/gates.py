"""Admission always rechecks the selected event and current shift under a lock."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from apps.accounts.models import GateAssignment
from apps.accounts.permissions import can_scan, can_supervise, can_manage_gate
from apps.events.models import Event
from .models import GateScanLog, Ticket, Order, OrderStatus, TicketStatus
from .services import admit_ticket


@transaction.atomic
def scan_for_event(user, event_id, serial):
    event = Event.objects.select_for_update().filter(pk=event_id).first()
    if not event or not can_scan(user, event_id):
        return {'ok': False, 'result': 'not_assigned'}, 403
    # Global access edits also lock/delete this row, so cannot race the admission.
    assignment = GateAssignment.objects.select_for_update().filter(user=user, event=event).first()
    if not can_scan(user, event_id):
        return {'ok': False, 'result': 'not_assigned'}, 403
    label = assignment.gate_label if assignment else 'Event operations'
    ticket = Ticket.objects.select_related('order_item__order', 'order_item__ticket_type').filter(serial=serial).first()
    if not ticket:
        result, status = 'not_found', 404
    elif ticket.order_item.order.event_id != event_id:
        result, status = 'wrong_event', 409
        ticket = None  # Never put another client's ticket or buyer in this event's log.
    else:
        order = Order.objects.select_for_update().get(pk=ticket.order_item.order_id)
        if not can_scan(user, event_id):
            return {'ok': False, 'result': 'not_assigned'}, 403
        if order.status != OrderStatus.PAID:
            result, status = 'unpaid', 409
        elif admit_ticket(ticket, user, timezone.now()):
            result, status = 'checked_in', 200
        else:
            ticket.refresh_from_db()
            result, status = ('already_used' if ticket.status == TicketStatus.USED else 'cancelled'), 409
    GateScanLog.objects.create(event=event, actor=user, ticket=ticket, result=result, gate_label=label)
    body = {'ok': result == 'checked_in', 'result': result}
    if ticket:
        ticket.refresh_from_db(fields=['checked_in_at'])
        body.update(buyer_name=ticket.order_item.order.buyer_name,
                    ticket_type=ticket.order_item.ticket_type.name, event_title=event.title,
                    checked_in_at=timezone.localtime(ticket.checked_in_at).strftime('%H:%M:%S') if ticket.checked_in_at else None)
    return body, status


@never_cache
@login_required(login_url='accounts:login')
@require_POST
def select_event(request, event_id):
    if not can_scan(request.user, event_id):
        raise PermissionDenied('This event is not available during your current shift.')
    request.session['gate_event_id'] = event_id
    return redirect('tickets:scanner_event', event_id=event_id)


@never_cache
@login_required(login_url='accounts:login')
def supervisor(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if not can_supervise(request.user, event):
        raise PermissionDenied
    logs = event.gate_scans.select_related('actor', 'ticket__order_item__ticket_type')
    tickets = Ticket.objects.filter(order_item__order__event=event, order_item__order__status=OrderStatus.PAID)
    results = list(logs.values('result').annotate(count=Count('id')).order_by('result'))
    for row in results:
        row['label'] = GateScanLog.RESULT_LABELS.get(row['result'], 'Other entry check')
    return render(request, 'gates/supervisor.html', {'event': event,
        'admitted': tickets.filter(status=TicketStatus.USED).count(),
        'remaining': tickets.filter(status=TicketStatus.VALID).count(),
        'results': results,
        'guards': logs.filter(result='checked_in').values('actor__username', 'gate_label').annotate(count=Count('id')).order_by('-count'),
        'logs': Paginator(logs, 50).get_page(request.GET.get('page')),
        'can_manage': can_manage_gate(request.user, event), 'checked_at': timezone.now()})
