"""Minimal per-IP request throttle backed by Django's cache framework.

Not a full library (no django-ratelimit dependency) — just enough to close
the "no throttling anywhere in the app" gap on the handful of endpoints that
actually need it: order/ticket lookups (PII + QR exposure via guessed
references) and the staff login form (credential stuffing / brute force).

Uses whatever CACHES['default'] is configured — LocMemCache by default,
which is per-process. That's a real limitation under multiple gunicorn
workers (each worker has its own counter), but it's still a meaningful
first line of defense and costs nothing to add. For multi-worker production
deployments, point CACHES at a shared backend (e.g. Redis) so the limit is
enforced globally rather than per-worker.
"""
import functools

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


def _client_ip(request):
    """X-Forwarded-For is attacker-controlled unless a trusted reverse proxy
    sits in front and appends to it — trusting it blindly (or trusting the
    wrong end of the chain) lets anyone rotate the header per request and get
    a fresh rate-limit bucket every time, which defeats the whole point of
    this module. Default is REMOTE_ADDR only; only trust the header, and only
    the correct number of hops from the right, if TRUSTED_PROXY_COUNT is
    explicitly set for this deployment's actual proxy topology."""
    trusted_hops = getattr(settings, 'TRUSTED_PROXY_COUNT', 0)
    if trusted_hops > 0:
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            chain = [ip.strip() for ip in forwarded.split(',') if ip.strip()]
            if len(chain) >= trusted_hops:
                return chain[-trusted_hops]
    return request.META.get('REMOTE_ADDR', 'unknown')


def ratelimit(*, key_prefix: str, limit: int, window_seconds: int, key_kwarg: str = None):
    """Allow at most `limit` requests per client IP per `window_seconds`.
    Over the limit: plain 429 response (these are form-POST/lookup endpoints,
    not an API other services depend on, so a bare response is fine).

    `key_kwarg`: name of a URL kwarg (e.g. 'reference') to additionally scope
    the limit to a specific resource. Without this, every request from one
    IP shares a single bucket — fine for a login form, but wrong for a
    per-order lookup page: many real buyers behind the same NAT (a campus
    WiFi, for instance) would exhaust each other's quota just by each
    checking out their own, different order. Scoping by the resource keeps
    that working while still throttling repeated hits on one specific
    resource (a stress test found this the hard way — see apps/tickets/tests.py)."""
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapped(request, *args, **kwargs):
            scope = f':{kwargs[key_kwarg]}' if key_kwarg else ''
            cache_key = f'ratelimit:{key_prefix}:{_client_ip(request)}{scope}'
            count = cache.get(cache_key, 0)
            if count >= limit:
                return HttpResponse('Too many requests — please wait a moment and try again.', status=429)
            try:
                # incr() is atomic where the backend supports it (Redis, Memcached);
                # LocMemCache's incr() is also process-safe. It only raises when
                # the key doesn't exist yet, i.e. this is the first request in
                # the window — start a fresh counter with the window's TTL.
                cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, timeout=window_seconds)
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
