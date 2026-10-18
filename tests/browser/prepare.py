"""Seed only the isolated browser-test database; never touches the user's data."""
import os
import shutil
import sys
from datetime import timedelta
from pathlib import Path


def prepare():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.browser_test'

    import django
    django.setup()

    from django.core.management import call_command
    from django.utils import timezone
    from apps.events.models import Event, LineupItem
    from apps.tickets.models import TicketType

    call_command('migrate', verbosity=0, interactive=False)
    call_command('flush', verbosity=0, interactive=False)
    fixtures = [
        ('Coastal Sound Festival', 'coastal-sound-festival', 'festival', 'Kilifi', 'beach-cover.jpg', 7, True),
        ('Nairobi After Dark', 'nairobi-after-dark', 'nightlife', 'Nairobi', 'rooftop-cover.jpg', 2, False),
        ('Jazz Under the Stars', 'jazz-under-the-stars', 'concert', 'Mombasa', 'jazz-cover.jpg', 12, False),
        ('A Night of Comedy', 'a-night-of-comedy', 'comedy', 'Nairobi', 'comedy-cover.jpg', -7, False),
    ]
    media = Path('/tmp/serotix-browser-test-media/events/covers')
    media.mkdir(parents=True, exist_ok=True)
    for title, slug, category, city, cover, days, featured in fixtures:
        shutil.copyfile(Path('static/img/events') / cover, media / cover)
        event = Event.objects.create(
            title=title,
            slug=slug,
            category=category,
            city=city,
            venue=f'{city} Live Stage',
            description=(
                'A proper night out. Live music, good food and the people you came with.\n\n'
                'Doors open at 6 PM. Bring your QR ticket and get ready for the first set.'
            ),
            organizer_name='SeroTix Live',
            cover_image=f'events/covers/{cover}',
            start_at=timezone.now() + timedelta(days=days),
            is_featured=featured,
        )
        TicketType.objects.create(
            event=event,
            name='General admission',
            description='One night. All the good energy.',
            price='2000.50',
            quantity_total=40,
            max_per_order=3,
        )
        TicketType.objects.create(
            event=event,
            name='VIP',
            description='Your spot, a little closer to the action.',
            price='4500.00',
            quantity_total=8,
            max_per_order=2,
        )
        TicketType.objects.create(
            event=event,
            name='Early bird',
            price='1000.00',
            quantity_total=5,
            quantity_sold=5,
        )
        TicketType.objects.create(
            event=event,
            name='Closed release',
            price='750.00',
            quantity_total=4,
            sales_end=timezone.now() - timedelta(days=1),
        )
        LineupItem.objects.create(event=event, name='The Coastal Collective', role='Live band', time='8:00 PM')
    from django.contrib.auth import get_user_model
    from apps.accounts.models import AccountProfile, GateAssignment
    User = get_user_model()
    owner = User.objects.create_user('gate-owner', 'gate-owner@example.test', 'BrowserGate123!')
    AccountProfile.objects.create(user=owner, role='seller', business_name='Client A events')
    other = User.objects.create_user('gate-other-owner', 'gate-other@example.test', 'BrowserGate123!')
    AccountProfile.objects.create(user=other, role='seller', business_name='Client B events')
    for username in ['gate-invitee','gate-existing']:
        guard = User.objects.create_user(username, username+'@example.test', 'BrowserGate123!')
        AccountProfile.objects.create(user=guard, role='buyer')
    event = Event.objects.get(slug='coastal-sound-festival')
    event.owner=owner; event.theme='coastal'; event.save()
    other_event=Event.objects.get(slug='nairobi-after-dark')
    other_event.owner=other; other_event.save()
    GateAssignment.objects.create(user=User.objects.get(username='gate-existing'), event=event,
                                  is_supervisor=True, gate_label='North gate')
    # Private test tickets don't change public catalog counts or trigger mail.
    from apps.tickets.models import Order, OrderItem, Ticket
    from uuid import UUID
    for target, serial in [(event, '11111111-1111-4111-8111-111111111111'),
                           (other_event, '22222222-2222-4222-8222-222222222222')]:
        tier=target.ticket_types.get(name='General admission')
        order=Order.objects.create(event=target,status='paid',buyer_name='Gate fixture',buyer_phone='254700000099',total_amount=2000.50)
        item=OrderItem.objects.create(order=order,ticket_type=tier,quantity=1,unit_price=2000.50)
        Ticket.objects.create(order_item=item,serial=UUID(serial))
    print('Browser fixtures ready in /tmp/serotix-browser-tests.sqlite3; all payments simulated.')


if __name__ == '__main__':
    prepare()
