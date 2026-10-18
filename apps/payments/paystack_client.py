"""Minimal client for Paystack's Transactions API.

Calls the REST API directly with `requests` rather than a third-party SDK,
same reason as stripe_client.py/mpesa.py: the request/response shape stays
fully auditable in this file. Docs: https://paystack.com/docs/api/
"""
import hashlib
import hmac
import json

import requests
from django.conf import settings

API_BASE_URL = 'https://api.paystack.co'
REQUEST_TIMEOUT = 15  # seconds


class PaystackError(Exception):
    """Raised when the Paystack API rejects a request or is unreachable."""


class PaystackSignatureError(Exception):
    """Raised when a webhook's x-paystack-signature header doesn't verify."""


def initialize_transaction(*, order, reference: str, callback_url: str) -> dict:
    """One lump amount for the whole order (tickets + service fee) — unlike
    Stripe's Checkout Sessions, Paystack has no itemized line items, so there's
    no equivalent of the missing-service-fee-line-item bug to worry about here.

    `reference` must be unique per Paystack transaction attempt — the caller
    passes a payment-row-specific value (not bare order.reference), since an
    order can get more than one payment attempt."""
    secret_key = settings.PAYSTACK_SECRET_KEY
    if not order.buyer_email:
        raise PaystackError('An email address is required for card payment.')
    data = {
        'email': order.buyer_email,
        'amount': int(order.total_amount * 100),  # kobo/cents
        'currency': 'KES',
        'reference': reference,
        'callback_url': callback_url,
        'metadata': {'order_reference': order.reference},
    }

    try:
        resp = requests.post(
            f'{API_BASE_URL}/transaction/initialize',
            json=data,
            headers={'Authorization': f'Bearer {secret_key}'},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PaystackError(f'Could not reach Paystack Initialize Transaction endpoint: {exc}') from exc

    body = resp.json()
    if resp.status_code >= 400 or not body.get('status'):
        raise PaystackError(body.get('message') or str(body))
    return body['data']


def verify_transaction(reference: str) -> dict:
    secret_key = settings.PAYSTACK_SECRET_KEY
    try:
        resp = requests.get(
            f'{API_BASE_URL}/transaction/verify/{reference}',
            headers={'Authorization': f'Bearer {secret_key}'},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PaystackError(f'Could not reach Paystack Verify Transaction endpoint: {exc}') from exc

    body = resp.json()
    if resp.status_code >= 400 or not body.get('status'):
        raise PaystackError(body.get('message') or str(body))
    return body['data']


def verify_webhook_signature(payload: bytes, signature: str, secret_key: str) -> dict:
    """Paystack signs the raw request body with HMAC-SHA512 (no timestamp/replay
    window like Stripe's, so handle_paystack_event's own idempotency check —
    payment.status == COMPLETED short-circuiting — is what guards against replay)."""
    if not signature:
        raise PaystackSignatureError('Missing x-paystack-signature header')

    expected = hmac.new(secret_key.encode(), payload, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise PaystackSignatureError('Signature mismatch')

    return json.loads(payload)


def refund_transaction(reference: str) -> str:
    """Full refund (no amount passed). Returns the refund id."""
    secret_key = settings.PAYSTACK_SECRET_KEY
    try:
        resp = requests.post(
            f'{API_BASE_URL}/refund',
            json={'transaction': reference},
            headers={'Authorization': f'Bearer {secret_key}'},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PaystackError(f'Could not reach Paystack Refund endpoint: {exc}') from exc

    body = resp.json()
    if resp.status_code >= 400 or not body.get('status'):
        raise PaystackError(body.get('message') or str(body))
    return str(body['data'].get('id', reference))
