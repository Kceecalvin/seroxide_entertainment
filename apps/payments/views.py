import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.ratelimit import ratelimit
from apps.tickets.models import Order

from .paystack_client import PaystackSignatureError, verify_webhook_signature as verify_paystack_signature
from .services import (
    handle_paystack_event,
    handle_stk_callback,
    handle_stripe_event,
)
from .stripe_client import StripeSignatureError, verify_webhook_signature

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def mpesa_callback(request, token):
    """Webhook Safaricom calls once the customer accepts/rejects/times out the STK prompt.

    Safaricom's callback carries no authentication of its own, so the URL itself embeds a
    secret token (see MPESA_CALLBACK_TOKEN) that must match before we trust the payload.
    """
    if not settings.MPESA_CALLBACK_TOKEN or not hmac.compare_digest(token, settings.MPESA_CALLBACK_TOKEN):
        logger.warning('M-Pesa callback rejected: invalid or missing token')
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Rejected'}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        logger.warning('Unparseable M-Pesa callback body')
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid payload'}, status=400)

    handle_stk_callback(payload)
    # Daraja expects this exact acknowledgement shape regardless of our internal outcome.
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Webhook Stripe calls on checkout/payment events. Unlike M-Pesa, Stripe
    signs every request (Stripe-Signature header) — that signature, not a
    URL-embedded token, is what we trust here."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning('Stripe webhook received but STRIPE_WEBHOOK_SECRET is not configured — rejecting')
        return HttpResponse(status=403)

    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    try:
        event = verify_webhook_signature(request.body, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except StripeSignatureError as exc:
        logger.warning('Stripe webhook signature verification failed: %s', exc)
        return HttpResponse(status=400)

    handle_stripe_event(event)
    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """Webhook Paystack calls on charge events. Like Stripe, every request is
    signed (x-paystack-signature) — using your secret key directly, not a
    separate webhook secret."""
    if not settings.PAYSTACK_SECRET_KEY:
        logger.warning('Paystack webhook received but PAYSTACK_SECRET_KEY is not configured — rejecting')
        return HttpResponse(status=403)

    sig_header = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
    try:
        event = verify_paystack_signature(request.body, sig_header, settings.PAYSTACK_SECRET_KEY)
    except PaystackSignatureError as exc:
        logger.warning('Paystack webhook signature verification failed: %s', exc)
        return HttpResponse(status=400)

    handle_paystack_event(event)
    return HttpResponse(status=200)


@require_GET
@ratelimit(key_prefix='payment-status', limit=150, window_seconds=300)
@ratelimit(key_prefix='payment-status', limit=30, window_seconds=300, key_kwarg='reference')
def payment_status(request, reference):
    order = get_object_or_404(Order, reference=reference)
    from apps.tickets.access import require_order_access
    require_order_access(request, order)
    payment = order.payments.order_by('-created_at').first()
    return JsonResponse({
        'order_status': order.status,
        'payment_status': payment.status if payment else None,
        'result_desc': payment.result_desc if payment else '',
    })
