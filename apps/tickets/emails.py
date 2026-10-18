"""Order confirmation email — sent after fulfill_order() marks an order paid."""
import logging
from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from .access import order_access_url

logger = logging.getLogger(__name__)


def _deliver_order_confirmation(order, message_id=None):
    """Best-effort: a missing/broken email must never block ticket fulfilment."""
    if not order.buyer_email:
        return
    try:
        event = order.event
        items = list(
            order.items.select_related('ticket_type')
            .prefetch_related('tickets')
        )
        tickets = [t for item in items for t in item.tickets.all()]

        # Each ticket's QR is attached inline (Content-ID) rather than linked —
        # a scannable code that only shows up after the recipient clicks
        # "load images" isn't much of a scannable code.
        qr_attachments = []
        for i, ticket in enumerate(tickets):
            cid = f'ticket-qr-{i}'
            ticket.email_cid = cid if ticket.qr_code else None
            if ticket.qr_code:
                qr_attachments.append((cid, ticket.qr_code))

        context = {
            'order': order,
            'ticket_url': order_access_url(order),
            'event': event,
            'items': items,
            'tickets': tickets,
            'ticket_count': len(tickets),
            'headliner': event.lineup.first() if event.lineup.exists() else None,
            'site_name': settings.SITE_NAME,
            'site_domain': settings.SITE_DOMAIN,
            'support_email': settings.SITE_SUPPORT_EMAIL,
            'scheme': 'http' if settings.DEBUG else 'https',
        }
        html_body = render_to_string('emails/order_confirmation.html', context)
        text_body = render_to_string('emails/order_confirmation.txt', context)

        msg = EmailMultiAlternatives(
            subject=f"You're in — {event.title} | {settings.SITE_NAME}",
            body=text_body,
            from_email=f'{settings.SITE_NAME} <{settings.SITE_SUPPORT_EMAIL}>',
            to=[order.buyer_email],
            reply_to=[settings.SITE_SUPPORT_EMAIL],
            headers={'Message-ID': f'<serotix-{message_id}@{settings.SITE_DOMAIN}>'},
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.mixed_subtype = 'related'  # required for inline cid: images to render

        for cid, qr_field in qr_attachments:
            qr_field.open('rb')
            try:
                img = MIMEImage(qr_field.read(), _subtype='png')
            finally:
                qr_field.close()
            img.add_header('Content-ID', f'<{cid}>')
            img.add_header('Content-Disposition', 'inline', filename=f'{cid}.png')
            msg.attach(img)

        if msg.send(fail_silently=False) != 1:
            raise RuntimeError('Mail backend did not accept the message')
    except Exception:
        # Ticket fulfilment must never fail because of an email problem — log
        # and move on rather than raise.
        raise


def _deliver_waitlist(entry):
    """Best-effort, same reasoning as the order confirmation above — a
    broken email must never break the stock-release flow that triggers it."""
    try:
        ticket_type = entry.ticket_type
        event = ticket_type.event
        context = {
            'entry': entry,
            'ticket_type': ticket_type,
            'event': event,
            'site_name': settings.SITE_NAME,
            'site_domain': settings.SITE_DOMAIN,
            'support_email': settings.SITE_SUPPORT_EMAIL,
            'scheme': 'http' if settings.DEBUG else 'https',
        }
        html_body = render_to_string('emails/waitlist_spot_available.html', context)
        text_body = render_to_string('emails/waitlist_spot_available.txt', context)

        msg = EmailMultiAlternatives(
            subject=f"A {ticket_type.name} spot just opened up for {event.title}",
            body=text_body,
            from_email=f'{settings.SITE_NAME} <{settings.SITE_SUPPORT_EMAIL}>',
            to=[entry.email],
        )
        msg.attach_alternative(html_body, 'text/html')
        if msg.send(fail_silently=False) != 1:
            raise RuntimeError('Mail backend did not accept the message')
    except Exception:
        raise


def send_order_confirmation_email(order):
    from apps.core.mailer import queue_email
    return queue_email(recipient=order.buyer_email, subject=f'Tickets: {order.event.title}', kind='order',
                       payload={'order_id': order.pk}, key=f'order-confirmation:{order.pk}')


def send_waitlist_spot_available_email(entry):
    from apps.core.mailer import queue_email
    return queue_email(recipient=entry.email, subject=f'A spot opened for {entry.ticket_type.event.title}', kind='waitlist',
                       payload={'entry_id': entry.pk}, key=f'waitlist:{entry.pk}')
