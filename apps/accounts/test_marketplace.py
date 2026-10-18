from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import AccountProfile, GateAssignment
from apps.core.models import EmailDelivery
from apps.core.mailer import queue_email, deliver
from apps.events.models import Event
from apps.tickets.models import TicketType, Order, Ticket, OrderStatus
from apps.tickets.services import create_order, fulfill_order, release_order_stock, OrderError
from apps.tickets.access import order_access_url

User = get_user_model()


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', SITE_DOMAIN='serotix.co.ke')
class MarketplaceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.buyer = self.user('buyer')
        self.seller = self.user('seller', 'seller')
        self.other = self.user('other', 'seller')
        self.admin = self.user('admin', 'admin')
        self.scanner = self.user('scanner', 'scanner')
        self.owner = User.objects.create_superuser('owner', 'owner@example.test', 'CorrectHorseBattery99!')
        self.event = Event.objects.create(owner=self.seller, title='Seller night', description='A night to remember', venue='The Hall', start_at=timezone.now()+timedelta(days=10), review_status='draft', is_published=False, cover_image='events/covers/test.jpg')
        self.tier = TicketType.objects.create(event=self.event, name='General', price=1000, quantity_total=10)

    def user(self, name, role='buyer'):
        user = User.objects.create_user(name, f'{name}@example.test', 'CorrectHorseBattery99!')
        AccountProfile.objects.create(user=user, role=role, business_name=name+' events')
        return user

    def login(self, user): self.client.force_login(user)

    def test_seller_onboarding_preserves_buyer_orders_and_cannot_elevate(self):
        self.login(self.buyer)
        response = self.client.post(reverse('accounts:seller_onboard'), {'business_name':'My studio', 'accepted':'on', 'role':'superadmin', 'is_superuser':'on'})
        self.assertEqual(response.status_code, 302)
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.account_profile.role, 'seller')
        self.assertFalse(self.buyer.is_superuser)

    def test_other_seller_cannot_edit_preview_submit_or_price_event(self):
        self.login(self.other)
        for route in ['seller_edit','seller_preview','seller_submit','seller_tier','seller_withdraw']:
            url=reverse('accounts:'+route,args=[self.event.pk])
            response=self.client.get(url) if route in ['seller_edit','seller_preview'] else self.client.post(url,{})
            self.assertEqual(response.status_code,404,route)

    def test_private_event_absent_from_detail_checkout_and_catalog(self):
        self.assertEqual(self.client.get(self.event.get_absolute_url()).status_code,404)
        self.assertEqual(self.client.post(reverse('tickets:checkout',args=[self.event.slug])).status_code,404)
        self.assertNotContains(self.client.get(reverse('events:catalog')), self.event.title)

    def test_submit_approve_and_live_edit_protection(self):
        self.login(self.seller)
        self.client.post(reverse('accounts:seller_submit',args=[self.event.pk]))
        self.event.refresh_from_db();self.assertEqual(self.event.review_status,'pending')
        self.assertEqual(self.client.post(reverse('accounts:seller_edit',args=[self.event.pk]), {'title':'Unreviewed change'}).status_code,403)
        self.login(self.admin)
        self.client.post(reverse('dashboard:review',args=[self.event.pk]), {'decision':'approved'})
        self.event.refresh_from_db();self.assertTrue(self.event.is_published)
        self.assertEqual(self.client.get(self.event.get_absolute_url()).status_code,200)
        self.login(self.seller)
        self.assertEqual(self.client.post(reverse('accounts:seller_tier',args=[self.event.pk]), {}).status_code,403)
        self.client.post(reverse('accounts:seller_withdraw',args=[self.event.pk]))
        self.event.refresh_from_db();self.assertFalse(self.event.is_published)

    def test_approval_requires_readiness_and_changes_need_explanation(self):
        self.event.review_status='pending';self.event.cover_image='';self.event.save()
        self.login(self.admin)
        self.client.post(reverse('dashboard:review',args=[self.event.pk]),{'decision':'approved'})
        self.event.refresh_from_db();self.assertFalse(self.event.is_published)
        self.client.post(reverse('dashboard:review',args=[self.event.pk]),{'decision':'changes'})
        self.event.refresh_from_db();self.assertEqual(self.event.review_status,'pending')
        self.client.post(reverse('dashboard:review',args=[self.event.pk]),{'decision':'changes','note':'Please add cover artwork.'})
        self.event.refresh_from_db();self.assertEqual(self.event.review_status,'changes')
        self.assertEqual(EmailDelivery.objects.count(),1)

    def test_admin_cannot_change_team_or_refund_but_can_review(self):
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse('dashboard:reviews')).status_code,200)
        self.assertNotEqual(self.client.get(reverse('dashboard:team')).status_code,200)
        self.assertNotEqual(self.client.get(reverse('dashboard:payment_reconciliation')).status_code,200)
        self.assertNotEqual(self.client.get('/secure-admin-panel/').status_code,200)

    def test_only_owner_can_assign_scanner(self):
        data={'user':self.scanner.pk,'role':'scanner','events':[self.event.pk]}
        self.login(self.admin);self.client.post(reverse('dashboard:team'),data)
        self.assertEqual(GateAssignment.objects.count(),0)
        self.login(self.owner);self.client.post(reverse('dashboard:team'),data)
        self.assertTrue(GateAssignment.objects.filter(user=self.scanner,event=self.event).exists())
        self.client.post(reverse('dashboard:team'),{'user':self.scanner.pk,'role':'buyer'})
        self.assertFalse(GateAssignment.objects.filter(user=self.scanner).exists())

    def paid_order(self):
        self.event.review_status='approved';self.event.is_published=True;self.event.save()
        order=create_order(event=self.event,buyer=self.buyer,buyer_name='Test',buyer_email='buyer@example.test',buyer_phone='254700000001',cart={self.tier.pk:1})
        fulfill_order(order);order.refresh_from_db();return order

    def test_scanner_assignment_and_paid_state_and_audit(self):
        order=self.paid_order();ticket=Ticket.objects.get(order_item__order=order)
        self.login(self.scanner);url=reverse('tickets:scanner_check',args=[ticket.serial])
        self.assertEqual(self.client.post(url).status_code,403)
        GateAssignment.objects.create(user=self.scanner,event=self.event)
        Order.objects.filter(pk=order.pk).update(status='cancelled')
        self.assertEqual(self.client.post(url).status_code,409)
        Order.objects.filter(pk=order.pk).update(status='paid')
        self.assertTrue(self.client.post(url).json()['ok'])
        self.assertFalse(self.client.post(url).json()['ok'])
        ticket.refresh_from_db();self.assertEqual(ticket.checked_in_by_id,self.scanner.pk)

    def test_order_reference_alone_does_not_expose_tickets_or_payment_status(self):
        order=self.paid_order()
        for name in ['tickets:order_success','tickets:order_pending','payments:status']:
            url=reverse(name,args=[order.reference])
            self.assertEqual(self.client.get(url).status_code,404)
            self.login(self.other);self.assertEqual(self.client.get(url).status_code,404);self.client.logout()
        self.login(self.buyer)
        self.assertEqual(self.client.get(reverse('tickets:order_success',args=[order.reference])).status_code,200)

    def test_signed_email_link_and_full_guest_lookup(self):
        order=self.paid_order();url=urlsplit(order_access_url(order))
        self.assertEqual(self.client.get(url.path+'?'+url.query).status_code,200)
        self.assertIn(order.reference,self.client.session['ticket_orders'])
        self.client.logout()
        self.client.get(reverse('tickets:my_tickets'),{'reference':order.reference,'buyer_phone':'1'})
        self.assertNotIn(order.reference,self.client.session.get('ticket_orders',[]))
        self.client.get(reverse('tickets:my_tickets'),{'reference':order.reference,'buyer_phone':'0700000001'})
        self.assertIn(order.reference,self.client.session['ticket_orders'])

    def test_late_payment_cannot_oversell_released_stock(self):
        self.event.review_status='approved';self.event.is_published=True;self.event.save()
        order=create_order(event=self.event,buyer_name='Test',buyer_email='',buyer_phone='254700000001',cart={self.tier.pk:1})
        release_order_stock(order,new_status=OrderStatus.EXPIRED)
        self.tier.quantity_sold=10;self.tier.save()
        with self.assertRaises(OrderError):fulfill_order(order)
        self.assertFalse(Ticket.objects.filter(order_item__order=order).exists())

    def test_bad_tier_and_negative_price_rejected(self):
        self.event.review_status='approved';self.event.is_published=True;self.event.save()
        with self.assertRaises(OrderError):create_order(event=self.event,buyer_name='T',buyer_email='',buyer_phone='254700000001',cart={'nope':1})
        self.event.review_status='draft';self.event.save()
        self.login(self.seller)
        self.client.post(reverse('accounts:seller_tier',args=[self.event.pk]),{'name':'Bad','price':'-100','quantity_total':1,'max_per_order':1})
        self.assertEqual(self.event.ticket_types.count(),1)

    def test_email_failure_durable_retry_and_duplicate_suppression(self):
        with patch('django.core.mail.EmailMultiAlternatives.send',side_effect=OSError('SMTP unavailable')):
            with self.captureOnCommitCallbacks(execute=True):
                item=queue_email(recipient='buyer@example.test',subject='Booking',text='Test',key='unique')
        item.refresh_from_db();self.assertEqual(item.status,'failed')
        self.assertTrue(deliver(item.pk))
        self.assertFalse(deliver(item.pk))
        self.assertEqual(len(mail.outbox),1)
        with self.captureOnCommitCallbacks(execute=True):queue_email(recipient='buyer@example.test',subject='Booking',text='Test',key='unique')
        self.assertEqual(len(mail.outbox),1)

    def test_password_reset_is_branded_single_use_and_non_enumerating(self):
        with self.captureOnCommitCallbacks(execute=True):
            response=self.client.post(reverse('accounts:password_reset'), {'email':self.buyer.email})
        self.assertRedirects(response,reverse('accounts:reset_done'))
        self.assertEqual(len(mail.outbox),1)
        self.assertIn('https://serotix.co.ke/account/reset/',mail.outbox[0].body)
        self.assertIn('text/html',str(mail.outbox[0].alternatives))
        absent=self.client.post(reverse('accounts:password_reset'), {'email':'absent@example.test'})
        self.assertEqual(absent.url,response.url)
        import re
        reset_path = re.search(r'https://serotix.co.ke(/account/reset/\S+)', mail.outbox[0].body).group(1)
        link = self.client.get(reset_path)
        self.assertEqual(link.status_code, 302)
        changed = self.client.post(link.url, {'new_password1':'NewBuyerPassword-884!', 'new_password2':'NewBuyerPassword-884!'})
        self.assertRedirects(changed, reverse('accounts:reset_complete'))
        self.buyer.refresh_from_db()
        self.assertTrue(self.buyer.check_password('NewBuyerPassword-884!'))
        replay = Client().get(reset_path)
        self.assertContains(replay, 'expired or was already used')

    def test_marketplace_pages_render_for_each_role(self):
        for user,names in [(self.buyer,['accounts:my_account','accounts:seller_onboard']), (self.seller,['accounts:seller_home','accounts:seller_create']), (self.admin,['dashboard:reviews']), (self.owner,['dashboard:team','dashboard:emails'])]:
            self.login(user)
            for name in names:self.assertEqual(self.client.get(reverse(name)).status_code,200,name)
        self.login(self.seller)
        for name in ['accounts:seller_edit','accounts:seller_preview']:
            self.assertEqual(self.client.get(reverse(name,args=[self.event.pk])).status_code,200)

    def test_card_callback_requires_exact_amount_and_currency(self):
        from apps.payments.models import Payment, PaymentStatus
        from apps.payments.services import handle_paystack_event
        self.event.review_status='approved';self.event.is_published=True;self.event.save()
        for amount,currency in [(99999,'KES'),(100000,'USD')]:
            order=create_order(event=self.event,buyer_name='T',buyer_email='',buyer_phone='254700000001',cart={self.tier.pk:1})
            payment=Payment.objects.create(order=order,amount=order.total_amount,method='paystack',paystack_reference=f'precision-{order.pk}')
            handle_paystack_event({'event':'charge.success','data':{'reference':payment.paystack_reference,'status':'success','amount':amount,'currency':currency}})
            payment.refresh_from_db();self.assertEqual(payment.status,PaymentStatus.FAILED)
            self.assertFalse(Ticket.objects.filter(order_item__order=order).exists())

    def test_refunded_callback_cannot_reactivate_booking(self):
        from apps.payments.models import Payment, PaymentStatus
        from apps.payments.services import handle_paystack_event
        order=self.paid_order()
        Order.objects.filter(pk=order.pk).update(status='cancelled')
        Ticket.objects.filter(order_item__order=order).update(status='cancelled')
        payment=Payment.objects.create(order=order,amount=order.total_amount,method='paystack',paystack_reference='already-refunded',status=PaymentStatus.REFUNDED)
        handle_paystack_event({'event':'charge.success','data':{'reference':'already-refunded','status':'success','amount':100000,'currency':'KES'}})
        payment.refresh_from_db();order.refresh_from_db()
        self.assertEqual(payment.status,PaymentStatus.REFUNDED);self.assertEqual(order.status,'cancelled')
        self.assertFalse(Ticket.objects.filter(order_item__order=order,status='valid').exists())

    def test_late_payment_reacquires_available_stock(self):
        self.event.review_status='approved';self.event.is_published=True;self.event.save()
        order=create_order(event=self.event,buyer_name='T',buyer_email='',buyer_phone='254700000001',cart={self.tier.pk:1})
        release_order_stock(order,new_status=OrderStatus.EXPIRED)
        fulfill_order(order)
        self.tier.refresh_from_db();self.assertEqual(self.tier.quantity_sold,1)
        self.assertEqual(Ticket.objects.filter(order_item__order=order).count(),1)

    def test_seller_draft_creation_ignores_privileged_fields(self):
        self.login(self.seller)
        response=self.client.post(reverse('accounts:seller_create'), {
            'title':'A brand new night','category':'concert','description':'Live music for the city.',
            'organizer_name':'My event brand','venue':'The Hall','city':'Nairobi',
            'start_at':(timezone.now()+timedelta(days=20)).strftime('%Y-%m-%dT%H:%M'),
            'owner':self.other.pk,'review_status':'approved','is_published':'on','is_featured':'on',
        })
        self.assertEqual(response.status_code,302)
        created=Event.objects.get(title='A brand new night')
        self.assertEqual(created.owner_id,self.seller.pk)
        self.assertEqual(created.review_status,'draft')
        self.assertFalse(created.is_published);self.assertFalse(created.is_featured)
        edit=self.client.get(reverse('accounts:seller_edit',args=[created.pk]))
        self.assertEqual(edit.context['form'].initial['organizer_name'],'My event brand')

    def test_seller_reports_commission_without_deducting_processing(self):
        from decimal import Decimal
        self.paid_order()
        Order.objects.create(event=self.event, status='cancelled', total_amount=10000,
                                           platform_commission=500, buyer_name='Refunded', buyer_phone='254700000001')
        self.login(self.seller)
        response = self.client.get(reverse('accounts:seller_home'))
        self.assertEqual(response.context['sales']['tickets'], Decimal('1000'))
        self.assertEqual(response.context['sales']['commission'], Decimal('50'))
        self.assertEqual(response.context['sales']['organizer_share'], Decimal('950'))
        self.assertContains(response, 'not transferred payouts')
        self.login(self.owner)
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.context['metrics']['platform_fees'], Decimal('50'))
        self.assertEqual(response.context['metrics']['organizer_share'], Decimal('950'))
