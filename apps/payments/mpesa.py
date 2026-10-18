"""Minimal client for Safaricom's Daraja API (OAuth + STK Push / Lipa na M-Pesa Online).

Calls the REST API directly with `requests` rather than a third-party wrapper so the
request/response shape is fully auditable. Docs: https://developer.safaricom.co.ke/
"""
import base64
from datetime import datetime

import requests
from django.conf import settings
from django.core.cache import cache

SANDBOX_BASE_URL = 'https://sandbox.safaricom.co.ke'
PRODUCTION_BASE_URL = 'https://api.safaricom.co.ke'
CACHE_KEY = 'mpesa_access_token'
REQUEST_TIMEOUT = 15  # seconds


class MpesaError(Exception):
    """Raised when the Daraja API rejects a request or is unreachable."""


class MpesaClient:
    def __init__(self):
        self.base_url = PRODUCTION_BASE_URL if settings.MPESA_ENV == 'production' else SANDBOX_BASE_URL
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.shortcode = settings.MPESA_SHORTCODE
        self.passkey = settings.MPESA_PASSKEY
        # The token is appended here (rather than requiring it baked into the .env value)
        # so it's always in sync with the URL route that checks it — see payments/urls.py.
        self.callback_url = settings.MPESA_CALLBACK_URL.rstrip('/') + f'/{settings.MPESA_CALLBACK_TOKEN}/'

    def _get_access_token(self) -> str:
        token = cache.get(CACHE_KEY)
        if token:
            return token
        try:
            resp = requests.get(
                f'{self.base_url}/oauth/v1/generate',
                params={'grant_type': 'client_credentials'},
                auth=(self.consumer_key, self.consumer_secret),
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise MpesaError(f'Could not reach Daraja OAuth endpoint: {exc}') from exc

        data = resp.json()
        token = data.get('access_token')
        if not token:
            raise MpesaError(f'Daraja OAuth response missing access_token: {data}')
        # Daraja tokens are valid ~3600s; refresh a little early.
        cache.set(CACHE_KEY, token, timeout=int(data.get('expires_in', 3599)) - 60)
        return token

    def stk_push(self, *, phone_number: str, amount, account_reference: str, transaction_desc: str) -> dict:
        """Trigger an STK ("Lipa na M-Pesa Online") prompt on the customer's phone."""
        token = self._get_access_token()
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(
            f'{self.shortcode}{self.passkey}{timestamp}'.encode()
        ).decode()

        payload = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(round(float(amount))),
            'PartyA': phone_number,
            'PartyB': self.shortcode,
            'PhoneNumber': phone_number,
            'CallBackURL': self.callback_url,
            'AccountReference': account_reference[:20],
            'TransactionDesc': transaction_desc[:100],
        }

        try:
            resp = requests.post(
                f'{self.base_url}/mpesa/stkpush/v1/processrequest',
                json=payload,
                headers={'Authorization': f'Bearer {token}'},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise MpesaError(f'Could not reach Daraja STK push endpoint: {exc}') from exc

        data = resp.json()
        if resp.status_code != 200 or data.get('ResponseCode') not in (0, '0'):
            raise MpesaError(data.get('errorMessage') or data.get('ResponseDescription') or str(data))
        return data
