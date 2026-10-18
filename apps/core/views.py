import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from apps.core.ratelimit import ratelimit

from .forms import ContactForm

logger = logging.getLogger(__name__)


def health_check(request):
    """Plain liveness/readiness probe for uptime monitors and load balancers —
    confirms the app can actually reach its database, not just that the
    process is running."""
    from django.db import connection
    from django.http import JsonResponse
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return JsonResponse({'status': 'ok'})
    except Exception:
        # Log the real exception internally — never return it. An
        # unauthenticated caller reaching this endpoint during a DB outage
        # must not learn our database host/user/socket path from a
        # leaked traceback string (a pentest finding: SEC-03).
        logger.exception('Health check failed')
        return JsonResponse({'status': 'error', 'detail': 'Database connection failed'}, status=503)


@ratelimit(key_prefix='contact-form', limit=10, window_seconds=600)
def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            contact_message = form.save()
            from .mailer import queue_email
            queue_email(
                recipient=settings.SITE_SUPPORT_EMAIL,
                subject=f'[Contact] {contact_message.subject or "New message"}',
                text=f'From: {contact_message.name} <{contact_message.email}>\n\n{contact_message.message}',
                html=render_to_string('emails/contact_notification.html', {
                    'contact': contact_message, 'site_name': settings.SITE_NAME,
                    'site_domain': settings.SITE_DOMAIN, 'support_phone': settings.SITE_SUPPORT_PHONE, 'support_phone_tel': settings.SITE_SUPPORT_PHONE_TEL,
                    'support_email': settings.SITE_SUPPORT_EMAIL, 'scheme': 'https',
                }), payload={'reply_to': contact_message.email}, key=f'contact:{contact_message.pk}',
            )
            messages.success(request, "Thanks — we've got your message and will get back to you soon.")
            return redirect('contact')
    else:
        enquiry = request.GET.get('enquiry', '')
        subjects = {'host': 'I want to host an event', 'promote': 'Promote my event on SeroTix', 'group': 'Group booking enquiry'}
        form = ContactForm(initial={'subject': subjects.get(enquiry, '')})

    return render(request, 'core/contact.html', {'form': form})
