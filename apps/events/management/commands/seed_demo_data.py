from datetime import timedelta

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.events.models import Event, EventCategory, EventImage, LineupItem
from apps.tickets.models import TicketType

IMG_DIR = settings.BASE_DIR / 'static' / 'img' / 'events'

DEMO_EVENTS = [
    {
        'title': 'Nairobi Sunset Sessions',
        'category': EventCategory.NIGHTLIFE,
        'description': (
            'An open-air rooftop night of Afrobeat, amapiano and deep house as the sun goes down '
            'over the city. Resident DJs, a full cocktail bar, and a skyline view unlike anywhere '
            'else in Nairobi.\n\n'
            'Doors open at 6pm for golden-hour drinks before the decks properly get going at 8. '
            'Dress code is smart-casual — no sportswear at the door. VIP tickets include a reserved '
            'lounge table and a bottle of your choice.'
        ),
        'venue': 'Two Rivers Rooftop',
        'city': 'Nairobi',
        'days_out': 12,
        'is_featured': True,
        'ticket_types': [
            ('Regular', 1500, 200),
            ('VIP', 4500, 40),
        ],
        'cover': 'rooftop-cover.jpg',
        'gallery': ['rooftop-gallery-1.jpg', 'rooftop-gallery-2.jpg'],
        'lineup': [
            ('DJ Kaka', 'Opening set', '6:00 PM'),
            ('Mena', 'Amapiano', '8:00 PM'),
            ('DJ Joe Mfalme', 'Headliner', '10:30 PM'),
        ],
    },
    {
        'title': 'Kilifi Beach Festival',
        'category': EventCategory.FESTIVAL,
        'description': (
            'Three days on the sand: live bands, international DJs, food stalls and camping. '
            "Kenya's biggest coastal music festival returns for another year of sun and bass.\n\n"
            'Bring a tent or book one of the beachfront cabanas — gates open Friday at noon and the '
            'music runs straight through Sunday night. Weekend Pass holders get free camping; VVIP '
            'Cabana includes a private shaded area for up to 6 people right at the front of the main stage.'
        ),
        'venue': 'Bofa Beach',
        'city': 'Kilifi',
        'days_out': 30,
        'is_featured': True,
        'ticket_types': [
            ('Day Pass', 2000, 500),
            ('Weekend Pass', 5000, 300),
            ('VVIP Cabana', 15000, 20),
        ],
        'cover': 'beach-cover.jpg',
        'gallery': ['beach-gallery-1.jpg', 'beach-gallery-2.jpg'],
        'lineup': [
            ('Sauti Sol', 'Friday headliner', 'Fri, 9:00 PM'),
            ('Nyashinski', 'Saturday headliner', 'Sat, 9:30 PM'),
            ('Coast DJ Collective', 'Beach stage all weekend', 'Fri–Sun'),
        ],
    },
    {
        'title': 'Comedy Kingdom Live',
        'category': EventCategory.COMEDY,
        'description': (
            "A night of stand-up from Kenya's sharpest comedians, plus a surprise headline guest. "
            'Doors open early — come hungry, the food trucks are outside.\n\n'
            'Expect two hours of sets from the local circuit\'s best, MC\'d live, with a short interval '
            'for drinks. This one sells out fast — get tickets early if you want a table near the front.'
        ),
        'venue': 'Alliance Française',
        'city': 'Nairobi',
        'days_out': 6,
        'is_featured': False,
        'ticket_types': [
            ('Standard', 1000, 150),
        ],
        'cover': 'comedy-cover.jpg',
        'gallery': ['comedy-gallery-1.jpg'],
        'lineup': [
            ('MC Tricky', 'Host', '7:00 PM'),
            ('Njambi K', 'Support', '7:30 PM'),
            ('Churchill', 'Headliner', '8:30 PM'),
        ],
    },
    {
        'title': 'Mombasa Jazz & Blues Night',
        'category': EventCategory.CONCERT,
        'description': (
            'An intimate evening of live jazz and blues on the Mombasa waterfront, featuring '
            'local and regional acts across two stages.\n\n'
            'Table for 4 tickets include a reserved table with waterfront views and a shared platter. '
            'The evening opens with a warm-up set at sunset before the main stage takes over after dark.'
        ),
        'venue': 'Nyali Waterfront Gardens',
        'city': 'Mombasa',
        'days_out': 20,
        'is_featured': False,
        'ticket_types': [
            ('Regular', 1800, 250),
            ('Table for 4', 12000, 15),
        ],
        'cover': 'jazz-cover.jpg',
        'gallery': ['jazz-gallery-1.jpg', 'jazz-gallery-2.jpg'],
        'lineup': [
            ('The Waterfront Quartet', 'Sunset warm-up', '6:30 PM'),
            ('Coast Blues Collective', 'Main stage', '8:00 PM'),
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed/refresh demo events, ticket types, photos, and lineups for local development.'

    def handle(self, *args, **options):
        created, updated = 0, 0
        for data in DEMO_EVENTS:
            try:
                event = Event.objects.get(title=data['title'])
                is_new = False
            except Event.DoesNotExist:
                event = Event(
                    title=data['title'],
                    start_at=timezone.now() + timedelta(days=data['days_out'], hours=3),
                )
                is_new = True

            event.category = data['category']
            event.description = data['description']
            event.venue = data['venue']
            event.city = data['city']
            event.is_featured = data['is_featured']
            event.save()

            created += is_new
            updated += not is_new

            if not event.ticket_types.exists():
                for name, price, qty in data['ticket_types']:
                    TicketType.objects.create(event=event, name=name, price=price, quantity_total=qty)

            cover_path = IMG_DIR / data['cover']
            if cover_path.exists() and not event.cover_image:
                with open(cover_path, 'rb') as f:
                    event.cover_image.save(data['cover'], File(f), save=True)

            if not event.gallery.exists():
                for i, filename in enumerate(data['gallery']):
                    path = IMG_DIR / filename
                    if path.exists():
                        img = EventImage(event=event, order=i)
                        with open(path, 'rb') as f:
                            img.image.save(filename, File(f), save=True)

            if not event.lineup.exists():
                for i, (name, role, time_str) in enumerate(data['lineup']):
                    LineupItem.objects.create(event=event, name=name, role=role, time=time_str, order=i)

        self.stdout.write(self.style.SUCCESS(f'Seeded {created} new event(s), refreshed {updated} existing.'))
