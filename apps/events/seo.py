"""schema.org Event structured data (JSON-LD) for search engines.

Google's rich-result event listings (date/venue/ticket price shown directly in search)
come from this — see https://developers.google.com/search/docs/appearance/structured-data/event.
"""
import json

from django.core.serializers.json import DjangoJSONEncoder


def event_json_ld(event, ticket_types, request) -> str:
    address = {
        '@type': 'PostalAddress',
        'addressLocality': event.city,
        'addressCountry': 'KE',
    }
    if event.address:
        address['streetAddress'] = event.address

    data = {
        '@context': 'https://schema.org',
        '@type': 'Event',
        'name': event.title,
        'startDate': event.start_at.isoformat(),
        'eventStatus': 'https://schema.org/EventScheduled',
        'eventAttendanceMode': 'https://schema.org/OfflineEventAttendanceMode',
        'location': {'@type': 'Place', 'name': event.venue, 'address': address},
        'description': event.description,
        'organizer': {'@type': 'Organization', 'name': event.organizer_name},
    }
    if event.end_at:
        data['endDate'] = event.end_at.isoformat()
    if event.cover_image:
        data['image'] = [request.build_absolute_uri(event.cover_image.url)]

    offers = [
        {
            '@type': 'Offer',
            'name': t.name,
            'price': str(t.price),
            'priceCurrency': 'KES',
            'availability': (
                'https://schema.org/InStock' if t.remaining > 0 else 'https://schema.org/SoldOut'
            ),
            'url': request.build_absolute_uri(event.get_absolute_url()),
        }
        for t in ticket_types
    ]
    if offers:
        data['offers'] = offers

    # A literal "</script" inside the JSON string would prematurely close the tag it's embedded
    # in — escape the slash so the browser's HTML parser can't misread it as a close tag.
    return json.dumps(data, cls=DjangoJSONEncoder).replace('</script', '<\\/script')
