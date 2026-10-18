from urllib.parse import urlencode
from django.conf import settings
from django.core import signing
from django.http import Http404
from django.urls import reverse
from apps.accounts.permissions import is_admin


def grant_order(request, order):
    references = request.session.get('ticket_orders', [])
    request.session['ticket_orders'] = list(dict.fromkeys([*references, order.reference]))[-50:]


def order_access_url(order):
    token = signing.dumps({'order': order.pk, 'email': order.buyer_email}, salt='ticket-access')
    return f'https://{settings.SITE_DOMAIN}{reverse("tickets:order_success", args=[order.reference])}?{urlencode({"access": token})}'


def require_order_access(request, order):
    if request.user.is_authenticated and (order.buyer_id == request.user.pk or is_admin(request.user)):
        return
    if order.reference in request.session.get('ticket_orders', []):
        return
    token = request.GET.get('access', '')
    if token:
        try:
            data = signing.loads(token, salt='ticket-access', max_age=60 * 60 * 24 * 90)
            if data == {'order': order.pk, 'email': order.buyer_email}:
                grant_order(request, order)
                return
        except signing.BadSignature:
            pass
    raise Http404('Find your tickets using your reference and checkout phone number, or sign in to the account used at checkout.')
