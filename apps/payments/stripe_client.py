"""Minimal client for Stripe's Checkout Sessions API.

Calls the REST API directly with `requests` rather than the `stripe` SDK, for
the same reason as apps/payments/mpesa.py: the request/response shape stays
fully auditable in this file instead of hidden behind a dependency. Docs:
https://stripe.com/docs/api/checkout/sessions
"""
import hmac
import json
import time
from hashlib import sha256

import requests
from django.conf import settings

API_BASE_URL = 'https://api.stripe.com/v1'
REQUEST_TIMEOUT = 15  # seconds
WEBHOOK_TOLERANCE_SECONDS = 300  # reject signed events older than this (replay protection)


class StripeError(Exception):
    """Raised when the Stripe API rejects a request or is unreachable."""


class StripeSignatureError(Exception):
    """Raised when a webhook's Stripe-Signature header doesn't verify."""


def create_checkout_session(*, order, success_url: str, cancel_url: str) -> dict:
    """One line item per OrderItem (ticket type). KES is not a Stripe zero-decimal
    currency, so amounts are sent in cents."""
    secret_key = settings.STRIPE_SECRET_KEY
    data = {
        'mode': 'payment',
        'success_url': success_url,
        'cancel_url': cancel_url,
        'client_reference_id': order.reference,
        'payment_method_types[0]': 'card',
        'metadata[order_reference]': order.reference,
    }
    if order.buyer_email:
        data['customer_email'] = order.buyer_email

    items = list(order.items.select_related('ticket_type').all())
    for i, item in enumerate(items):
        data[f'line_items[{i}][quantity]'] = item.quantity
        data[f'line_items[{i}][price_data][currency]'] = 'kes'
        data[f'line_items[{i}][price_data][unit_amount]'] = int(item.unit_price * 100)
        data[f'line_items[{i}][price_data][product_data][name]'] = f'{order.event.title} — {item.ticket_type.name}'

    # Without its own line item, Stripe's amount_total would only ever equal
    # the ticket subtotal — permanently failing handle_stripe_event's amount
    # check against order.total_amount (tickets + fee) and cancelling every
    # single card order regardless of whether the card actually worked.
    if order.service_fee:
        fee_index = len(items)
        data[f'line_items[{fee_index}][quantity]'] = 1
        data[f'line_items[{fee_index}][price_data][currency]'] = 'kes'
        data[f'line_items[{fee_index}][price_data][unit_amount]'] = int(order.service_fee * 100)
        data[f'line_items[{fee_index}][price_data][product_data][name]'] = 'Service fee'

    try:
        resp = requests.post(
            f'{API_BASE_URL}/checkout/sessions',
            data=data,
            auth=(secret_key, ''),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise StripeError(f'Could not reach Stripe Checkout Sessions endpoint: {exc}') from exc

    body = resp.json()
    if resp.status_code >= 400:
        raise StripeError(body.get('error', {}).get('message') or str(body))
    return body


def verify_webhook_signature(payload: bytes, sig_header: str, webhook_secret: str) -> dict:
    """Verify a Stripe webhook per their documented scheme (Stripe-Signature:
    t=<timestamp>,v1=<hex hmac-sha256>) and return the parsed event dict.
    Raises StripeSignatureError on any failure — timing-safe comparison,
    explicit timestamp tolerance against replay."""
    if not sig_header:
        raise StripeSignatureError('Missing Stripe-Signature header')

    parts = dict(p.split('=', 1) for p in sig_header.split(',') if '=' in p)
    timestamp = parts.get('t')
    signature = parts.get('v1')
    if not timestamp or not signature:
        raise StripeSignatureError('Malformed Stripe-Signature header')

    try:
        if abs(time.time() - int(timestamp)) > WEBHOOK_TOLERANCE_SECONDS:
            raise StripeSignatureError('Webhook timestamp outside tolerance — possible replay')
    except ValueError:
        raise StripeSignatureError('Non-numeric timestamp in Stripe-Signature header') from None

    signed_payload = f'{timestamp}.'.encode() + payload
    expected = hmac.new(webhook_secret.encode(), signed_payload, sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise StripeSignatureError('Signature mismatch')

    return json.loads(payload)
