from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from .ratelimit import ratelimit


class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def _view(self, limit=3, window=60):
        @ratelimit(key_prefix='test-endpoint', limit=limit, window_seconds=window)
        def view(request):
            return HttpResponse('ok')
        return view

    def test_allows_requests_under_the_limit(self):
        view = self._view(limit=3)
        request = self.factory.get('/', REMOTE_ADDR='1.2.3.4')
        for _ in range(3):
            resp = view(request)
            self.assertEqual(resp.status_code, 200)

    def test_blocks_requests_over_the_limit(self):
        view = self._view(limit=3)
        request = self.factory.get('/', REMOTE_ADDR='1.2.3.4')
        for _ in range(3):
            view(request)
        resp = view(request)
        self.assertEqual(resp.status_code, 429)

    def test_limits_are_isolated_per_ip(self):
        view = self._view(limit=1)
        req_a = self.factory.get('/', REMOTE_ADDR='1.1.1.1')
        req_b = self.factory.get('/', REMOTE_ADDR='2.2.2.2')
        self.assertEqual(view(req_a).status_code, 200)
        self.assertEqual(view(req_b).status_code, 200, "a different IP's limit must not be shared")
        self.assertEqual(view(req_a).status_code, 429)

    def test_forwarded_for_is_ignored_by_default(self):
        """The exact bypass a security review flagged: spoofing X-Forwarded-For
        must not grant a fresh rate-limit bucket when TRUSTED_PROXY_COUNT=0."""
        view = self._view(limit=1)
        req1 = self.factory.get('/', REMOTE_ADDR='9.9.9.9', HTTP_X_FORWARDED_FOR='1.1.1.1')
        req2 = self.factory.get('/', REMOTE_ADDR='9.9.9.9', HTTP_X_FORWARDED_FOR='2.2.2.2')
        self.assertEqual(view(req1).status_code, 200)
        self.assertEqual(view(req2).status_code, 429, 'a spoofed X-Forwarded-For bypassed the rate limit')

    def test_key_kwarg_scopes_limit_per_resource_not_just_ip(self):
        """A stress test found this the hard way: many real buyers behind one
        shared IP (campus WiFi, a venue's NAT) each looking up their own,
        different order must not exhaust a limit meant for one resource."""
        @ratelimit(key_prefix='test-resource', limit=1, window_seconds=60, key_kwarg='reference')
        def view(request, reference):
            return HttpResponse('ok')

        request = self.factory.get('/', REMOTE_ADDR='9.9.9.9')
        self.assertEqual(view(request, reference='ORDER-A').status_code, 200)
        self.assertEqual(
            view(request, reference='ORDER-B').status_code, 200,
            "a different order's lookup must not be blocked by another order's quota, even from the same IP",
        )
        # But repeated hits on the SAME resource are still throttled.
        self.assertEqual(view(request, reference='ORDER-A').status_code, 429)


class ContactFormTests(TestCase):
    def test_submitting_saves_a_message(self):
        from .models import ContactMessage
        resp = self.client.post('/contact/', {
            'name': 'Jane', 'email': 'jane@example.com', 'subject': 'Hi', 'message': 'Hello there',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ContactMessage.objects.filter(email='jane@example.com').exists())

    def test_invalid_email_is_rejected(self):
        from .models import ContactMessage
        self.client.post('/contact/', {
            'name': 'Jane', 'email': 'not-an-email', 'subject': 'Hi', 'message': 'Hello there',
        })
        self.assertFalse(ContactMessage.objects.filter(name='Jane').exists())


class HealthCheckTests(TestCase):
    """Pentest finding (SEC-03): a DB outage must not leak connection
    internals (host/user/socket path) to an unauthenticated caller."""

    def test_db_failure_does_not_leak_exception_detail(self):
        from unittest.mock import patch
        with patch('django.db.connection.cursor', side_effect=Exception('password authentication failed for user "serotix" at host 10.0.0.5')):
            resp = self.client.get('/healthz/')
        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertEqual(body['detail'], 'Database connection failed')
        self.assertNotIn('10.0.0.5', body['detail'])
        self.assertNotIn('serotix', body['detail'])
