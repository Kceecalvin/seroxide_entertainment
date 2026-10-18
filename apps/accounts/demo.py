"""Local-only demo tools. These views are never mounted in normal deployments."""
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from apps.core.models import EmailDelivery
from apps.events.models import Event
from apps.tickets.models import Ticket

DEMO_PASSWORD = 'SeroTixDemo!2026'
DEMO_ACCOUNTS = [
    ('buyer', 'Buyer', 'Amara', 'Browse events, open bookings and view QR tickets.'),
    ('seller', 'Seller', 'Nia', 'Edit drafts, preview artwork, set prices and submit events.'),
    ('superadmin', 'Super Admin', 'Manuu', 'Manage team access, refunds, email delivery and reconciliation.'),
    ('admin', 'Admin', 'Alex', 'Review seller submissions and manage event operations.'),
    ('gate1', 'Gate scanner 1', 'Sam', 'Assigned to Blue Hour rooftop sessions.'),
    ('gate2', 'Gate scanner 2', 'Jo', 'Assigned to the Golden Coast festival.'),
    ('gate3', 'Gate scanner 3', 'Kai', 'Assigned to both demo events.'),
]


def enabled():
    return (getattr(settings, 'LOCAL_DEMO_ENABLED', False) and settings.DEBUG
            and settings.EMAIL_BACKEND == 'django.core.mail.backends.locmem.EmailBackend'
            and all(getattr(settings, key, False) for key in ('MPESA_SIMULATE', 'STRIPE_SIMULATE', 'PAYSTACK_SIMULATE'))
            and settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
            and str(settings.DATABASES['default']['NAME']) == '/tmp/serotix-browser-tests.sqlite3')


def guard():
    if not enabled():
        raise Http404


@never_cache
def hub(request):
    guard()
    accounts = [{'key': key, 'label': label, 'name': name, 'description': description,
                 'email': f'{key}@demo.serotix.test'} for key, label, name, description in DEMO_ACCOUNTS]
    return render(request, 'demo/hub.html', {
        'accounts': accounts, 'demo_password': DEMO_PASSWORD,
        'demo_events': Event.objects.filter(slug__startswith='demo-').order_by('start_at'),
        'demo_tickets': Ticket.objects.filter(order_item__order__reference__startswith='SRX-DEMO').select_related('order_item__order__event', 'order_item__ticket_type'),
        'demo_emails': EmailDelivery.objects.filter(key__startswith='demo-showcase:').order_by('pk'),
    })


@require_POST
@never_cache
def switch(request, key):
    guard()
    if key not in {row[0] for row in DEMO_ACCOUNTS}:
        raise Http404
    user = get_object_or_404(get_user_model(), username=f'{key}@demo.serotix.test', is_active=True)
    # No caller-supplied user IDs, redirects, passwords or roles are accepted.
    request.session.flush()
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('accounts:landing')


@never_cache
def email_preview(request, pk):
    guard()
    delivery = get_object_or_404(EmailDelivery, pk=pk, key__startswith='demo-showcase:')
    return render(request, 'demo/email.html', {'delivery': delivery})
