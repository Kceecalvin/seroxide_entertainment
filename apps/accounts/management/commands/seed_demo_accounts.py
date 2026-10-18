from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from apps.accounts.demo import enabled, DEMO_ACCOUNTS, DEMO_PASSWORD
from apps.accounts.models import AccountProfile, GateAssignment
from apps.events.models import Event, EventReview, LineupItem
from apps.tickets.models import Order, Ticket, TicketType
from apps.tickets.services import create_order, fulfill_order, release_order_stock
from apps.payments.models import Payment
from apps.core.models import EmailDelivery


class Command(BaseCommand):
    help = 'Create reusable sample accounts/events in the isolated local preview database only.'

    @transaction.atomic
    def handle(self, *args, **options):
        if not enabled():
            raise CommandError('Demo seeding requires the isolated browser_test database, simulated payments and memory-only email.')
        User = get_user_model()
        users = {}
        for key, label, name, _ in DEMO_ACCOUNTS:
            address = f'{key}@demo.serotix.test'
            user, created = User.objects.get_or_create(username=address, defaults={
                'email': address, 'first_name': name, 'last_name': '(Demo)',
                'is_superuser': key == 'superadmin', 'is_staff': key == 'superadmin',
            })
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
                role = 'scanner' if key.startswith('gate') else 'buyer' if key == 'superadmin' else key
                AccountProfile.objects.create(user=user, role=role, business_name='Afterglow Collective' if key == 'seller' else '')
            users[key] = user
        specs = [
            ('blue-hour', 'Blue Hour · Nairobi Rooftop', 'approved', 'nightlife', 'Nairobi', 'The Rooftop, Westlands', 7, 'slide-1.jpg', 1500),
            ('golden-coast', 'Golden Coast Festival', 'approved', 'festival', 'Mombasa', 'Oceanfront Gardens', 21, 'slide-2.jpg', 2500),
            ('red-room', 'The Red Room Sessions', 'pending', 'concert', 'Nairobi', 'Warehouse 19', 30, 'slide-3.jpg', 1800),
            ('sunday-social', 'Sunday Social · Unplugged', 'draft', 'concert', 'Nakuru', 'Garden House', 40, 'slide-4.jpg', 1200),
            ('after-dark', 'After Dark: City Edition', 'changes', 'nightlife', 'Nairobi', 'Skyline Lounge', 50, 'slide-5.jpg', 2000),
        ]
        events = {}
        for key, title, status, category, city, venue, days, image, price in specs:
            start = (timezone.now()+timedelta(days=days)).replace(hour=15, minute=0, second=0, microsecond=0)
            event, created = Event.objects.get_or_create(slug=f'demo-{key}', defaults={
                'title': title, 'owner': users['seller'], 'description': 'DEMO EXPERIENCE — a fictional listing for exploring SeroTix.\n\nLive sets, good food, and a crowd that feels like your people. Doors open at 6 PM. Bring your QR ticket and get ready for a night worth keeping.',
                'organizer_name': 'Afterglow Collective', 'category': category, 'city': city, 'venue': venue,
                'start_at': start, 'end_at': start+timedelta(hours=6), 'review_status': status,
                'is_published': status == 'approved', 'is_featured': key == 'blue-hour',
                'review_note': 'Please add the age restriction and a more detailed venue address before resubmitting.' if status == 'changes' else '',
            })
            if created:
                with open(settings.BASE_DIR/'static/img/hero'/image, 'rb') as source:
                    event.cover_image.save(f'demo-{key}.jpg', File(source))
                for tier_name, multiplier, capacity in [('Early Bird', 1, 80), ('Regular', 1.3, 200), ('VIP', 2, 35)]:
                    TicketType.objects.create(event=event, name=tier_name, price=Decimal(str(price))*Decimal(str(multiplier)), quantity_total=capacity, description='Demo admission — no real charge.')
                LineupItem.objects.create(event=event, name='The Afterglow Selectors', role='Demo lineup', time='8:00 PM')
                EventReview.objects.create(event=event, actor=users['admin'] if status in ('changes','approved') else users['seller'], status=status, note=event.review_note)
            events[key] = event
        for gate, keys in [('gate1',['blue-hour']), ('gate2',['golden-coast']), ('gate3',['blue-hour','golden-coast'])]:
            for key in keys:
                GateAssignment.objects.get_or_create(user=users[gate], event=events[key])

        for suffix, event_key, quantity, state in [('BLUE','blue-hour',3,'paid'), ('COAST','golden-coast',2,'paid'), ('PENDING','blue-hour',1,'pending'), ('CANCEL','golden-coast',1,'cancelled'), ('REFUND','blue-hour',1,'refunded')]:
            reference = f'SRX-DEMO-{suffix}'
            if Order.objects.filter(reference=reference).exists():
                continue
            event = events[event_key]
            tier = event.ticket_types.get(name='Early Bird')
            order = create_order(event=event, buyer=users['buyer'], buyer_name='Amara (Demo)', buyer_email=users['buyer'].email,
                                 buyer_phone='254700000099', cart={tier.pk:quantity})
            order.reference = reference
            order.save(update_fields=['reference'])
            payment = Payment.objects.create(order=order, amount=order.total_amount, method='mpesa', status='completed' if state in ('paid', 'refunded') else 'pending',
                                            mpesa_receipt_number='DEMO-'+suffix if state in ('paid', 'refunded') else '', result_desc='Local demo — no real payment was taken.')
            if state in ('paid', 'refunded'):
                fulfill_order(order)
                if state == 'refunded':
                    from apps.payments.refunds import issue_refund
                    issue_refund(payment, manual_reference='DEMO-RETURN-NO-REAL-MONEY')
                if suffix == 'BLUE':
                    ticket = Ticket.objects.filter(order_item__order=order).first()
                    ticket.status='used'; ticket.checked_in_at=timezone.now(); ticket.checked_in_by=users['gate1']
                    ticket.save(update_fields=['status','checked_in_at','checked_in_by'])
            elif state == 'cancelled':
                release_order_stock(order, new_status='cancelled')
                payment.status='failed'; payment.save(update_fields=['status'])
        # Stored visual samples are deliberately not handed to any mail backend.
        for key, heading, message, target in [
            ('welcome','Welcome to your next good night.','Your SeroTix account keeps your plans and tickets together. This is a sample welcome email.','accounts:my_account'),
            ('approved','Your event is live.','Blue Hour has been approved. Share your event page and invite your crowd. This is a sample approval email.','accounts:seller_home'),
            ('changes','One last polish before the spotlight.','Please add the age restriction and complete venue address, then submit again. This is a sample review email.','accounts:seller_home'),
        ]:
            context = {'heading':heading,'message':message,'action_url':'http://127.0.0.1:3050'+reverse(target),
                       'site_name':'SeroTix','site_domain':'127.0.0.1:3050','support_email':'support@demo.serotix.test','scheme':'http'}
            EmailDelivery.objects.get_or_create(key='demo-showcase:'+key, defaults={
                'recipient':users['buyer' if key=='welcome' else 'seller'].email, 'subject':heading,
                'text':render_to_string('emails/account_notice.txt',context), 'html':render_to_string('emails/account_notice.html',context),
                'status':'sent', 'sent_at':timezone.now(), 'attempts':1,
            })
        EmailDelivery.objects.get_or_create(key='demo-showcase:retry', defaults={
            'recipient':users['seller'].email, 'subject':'Sample failed email — try the retry button',
            'text':'Demo retry message. Local memory delivery only.', 'status':'failed', 'attempts':1, 'last_error':'DemoSMTPUnavailable',
        })
        self.stdout.write(self.style.SUCCESS('Seven demo accounts, five events, five bookings and email samples are ready.'))
