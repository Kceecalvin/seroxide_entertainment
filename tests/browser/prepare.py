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
    print('Browser fixtures ready in /tmp/serotix-browser-tests.sqlite3; all payments simulated.')


if __name__ == '__main__':
    prepare()
