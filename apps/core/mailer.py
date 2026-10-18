"""Persist transactional mail before sending; retry failures without blocking purchases.

SMTP cannot promise exactly-once delivery: a timeout after server acceptance can
produce a duplicate on retry. A stable Message-ID helps recipients deduplicate.
"""
import logging
from datetime import timedelta
from uuid import uuid4
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.utils import timezone
from .models import EmailDelivery

logger = logging.getLogger(__name__)


def queue_email(*, recipient, subject, text='', html='', kind='message', payload=None, key=None):
    if not recipient:
        return None
    mail, _ = EmailDelivery.objects.get_or_create(key=key or str(uuid4()), defaults={
        'recipient': recipient, 'subject': subject.replace('\r', ' ').replace('\n', ' ')[:250],
        'text': text, 'html': html, 'kind': kind, 'payload': payload or {},
    })
    transaction.on_commit(lambda: deliver(mail.pk), robust=True)
    return mail


def deliver(pk):
    now = timezone.now()
    eligible = Q(status__in=['pending', 'failed']) | Q(status='sending', updated_at__lt=now-timedelta(minutes=10))
    claimed = EmailDelivery.objects.filter(eligible, pk=pk, attempts__lt=5).update(status='sending', attempts=F('attempts')+1, updated_at=now)
    if not claimed:
        return False
    mail = EmailDelivery.objects.get(pk=pk)
    try:
        if mail.kind == 'order':
            from apps.tickets.models import Order
            from apps.tickets.emails import _deliver_order_confirmation
            _deliver_order_confirmation(Order.objects.get(pk=mail.payload['order_id']), message_id=mail.pk)
        elif mail.kind == 'waitlist':
            from apps.tickets.models import WaitlistEntry
            from apps.tickets.emails import _deliver_waitlist
            _deliver_waitlist(WaitlistEntry.objects.get(pk=mail.payload['entry_id']))
        else:
            msg = EmailMultiAlternatives(mail.subject, mail.text, settings.DEFAULT_FROM_EMAIL, [mail.recipient],
                reply_to=[mail.payload.get('reply_to') or settings.SITE_SUPPORT_EMAIL], headers={'Message-ID': f'<serotix-{mail.pk}@{settings.SITE_DOMAIN}>'})
            if mail.html: msg.attach_alternative(mail.html, 'text/html')
            if msg.send() != 1: raise RuntimeError('Mail backend did not accept the message')
    except Exception as exc:
        EmailDelivery.objects.filter(pk=pk).update(status='failed', last_error=type(exc).__name__, updated_at=timezone.now())
        logger.warning('Email delivery %s failed (%s)', pk, type(exc).__name__)
        return False
    EmailDelivery.objects.filter(pk=pk).update(status='sent', sent_at=timezone.now(), last_error='', updated_at=timezone.now())
    return True


def notify(user, subject, message, path):
    context = {'heading': subject, 'message': message, 'action_url': f'https://{settings.SITE_DOMAIN}{path}',
        'site_name': settings.SITE_NAME, 'site_domain': settings.SITE_DOMAIN,
        'support_email': settings.SITE_SUPPORT_EMAIL, 'scheme': 'https'}
    return queue_email(recipient=user if isinstance(user, str) else user.email, subject=f'{subject} | {settings.SITE_NAME}',
        text=render_to_string('emails/account_notice.txt', context), html=render_to_string('emails/account_notice.html', context))
