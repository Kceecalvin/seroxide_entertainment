"""Run on PostgreSQL: SQLite cannot prove row-lock behavior."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.utils import timezone
from apps.accounts.models import AccountProfile, GateAssignment
from apps.events.models import Event
from .models import Order, TicketType, Ticket
from .services import create_order, fulfill_order, OrderError
from .views import scanner_check


@skipUnless(connection.vendor == 'postgresql', 'Real row locks require PostgreSQL')
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ConcurrentTicketTests(TransactionTestCase):
    def setUp(self):
        self.event=Event.objects.create(title='Concurrency fixture', slug='concurrency-fixture',
            venue='Test venue',city='Nairobi',start_at=timezone.now()+timedelta(days=7))
        self.tier=TicketType.objects.create(event=self.event,name='Last ticket',price=1000,quantity_total=1)

    def reserve(self):
        return create_order(event=self.event,buyer_name='Fixture',buyer_email='',
            buyer_phone='254700000000',cart={str(self.tier.pk):1})

    def test_two_buyers_cannot_reserve_the_last_ticket(self):
        barrier=Barrier(2)
        def buy():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    self.reserve()
                    return 'reserved'
                except OrderError:
                    return 'sold out'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _:buy(),range(2)))
        self.assertCountEqual(results,['reserved','sold out'])
        self.tier.refresh_from_db()
        self.assertEqual(self.tier.quantity_sold,1)
        self.assertEqual(Order.objects.count(),1)

    def test_two_scanners_admit_only_one_person(self):
        order=self.reserve()
        fulfill_order(order)
        ticket=Ticket.objects.get(order_item__order=order)
        users=[]
        for i in range(2):
            user=get_user_model().objects.create_user(username=f'gate-fixture-{i}')
            AccountProfile.objects.create(user=user,role='scanner')
            GateAssignment.objects.create(user=user,event=self.event)
            users.append(user)
        barrier=Barrier(2)
        def scan(user):
            close_old_connections()
            try:
                request=RequestFactory().post('/tickets/scan/api/fixture/', {'event_id': self.event.pk}, REMOTE_ADDR=f'127.0.0.{user.pk}')
                request.user=user
                barrier.wait(timeout=10)
                return scanner_check(request,ticket.serial).content
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(scan,users))
        import json
        outcomes=[json.loads(x) for x in results]
        self.assertEqual(sum(x['ok'] for x in outcomes),1)
        self.assertEqual(sum(x['result']=='already_used' for x in outcomes),1)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status,'used')
        self.assertIn(ticket.checked_in_by_id,[u.pk for u in users])

    def test_revocation_committed_while_scan_waits_prevents_admission(self):
        from threading import Event as Signal
        from .models import GateScanLog
        order=self.reserve();fulfill_order(order)
        ticket=Ticket.objects.get(order_item__order=order)
        user=get_user_model().objects.create_user(username='revocation-fixture')
        assignment=GateAssignment.objects.create(user=user,event=self.event)
        locked, attempting = Signal(), Signal()
        def revoke():
            close_old_connections()
            try:
                with transaction.atomic():
                    Event.objects.select_for_update().get(pk=self.event.pk)
                    GateAssignment.objects.filter(pk=assignment.pk).update(revoked_at=timezone.now())
                    locked.set()
                    if not attempting.wait(10):raise RuntimeError('Scanner did not start')
            finally:close_old_connections()
        def scan():
            close_old_connections()
            try:
                if not locked.wait(10):raise RuntimeError('Revocation did not start')
                attempting.set()
                request=RequestFactory().post('/tickets/scan/api/fixture/', {'event_id':self.event.pk})
                request.user=user
                return scanner_check(request,ticket.serial).status_code
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            revoked=pool.submit(revoke);scanned=pool.submit(scan)
            revoked.result(timeout=15)
            self.assertEqual(scanned.result(timeout=15),403)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status,'valid')
        self.assertFalse(GateScanLog.objects.filter(result='checked_in').exists())
