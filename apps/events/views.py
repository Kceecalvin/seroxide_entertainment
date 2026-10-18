from datetime import timedelta

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Event, EventCategory
from .seo import event_json_ld


@require_GET
def discovery_catalog(request):
    """Public, bounded event data for the vibe finder and shared shortlists."""
    events = Event.objects.filter(is_published=True, start_at__gte=timezone.now()).prefetch_related('ticket_types')
    if 'slugs' in request.GET:
        slugs = list(dict.fromkeys(request.GET.get('slugs', '').split(',')))[:8]
        events = events.filter(slug__in=slugs)
    catalog = []
    for event in events.order_by('start_at', 'pk')[:48]:
        price = event.min_price
        catalog.append({
            'slug': event.slug, 'title': event.title,
            'category': event.category, 'categoryLabel': event.get_category_display(),
            'city': event.city, 'venue': event.venue,
            'date': timezone.localtime(event.start_at).strftime('%a, %d %b · %I:%M %p'),
            'startAt': event.start_at.isoformat(),
            'price': str(price) if price is not None else None,
            'available': event.total_remaining > 0,
            'image': event.cover_image.url if event.cover_image else static('img/hero/slide-3.jpg'),
            'url': event.get_absolute_url(),
        })
    response = JsonResponse({'events': catalog})
    response['Cache-Control'] = 'no-store'
    return response


def event_list(request):
    now = timezone.now()
    published = Event.objects.filter(is_published=True).prefetch_related('ticket_types')
    events = published

    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    city = request.GET.get('city', '').strip()
    when = request.GET.get('when', '').strip()
    sort = request.GET.get('sort', 'date')
    if when not in ('upcoming', 'weekend', 'month', 'past'):
        when = 'upcoming'

    if query:
        events = events.filter(
            Q(title__icontains=query) | Q(venue__icontains=query)
            | Q(description__icontains=query) | Q(city__icontains=query)
        )
    if category:
        events = events.filter(category=category)
    if city:
        events = events.filter(city__iexact=city)
    if when == 'past':
        events = events.filter(start_at__lt=now)
    else:
        events = events.filter(start_at__gte=now)
        local_now = timezone.localtime(now)
        if when == 'weekend':
            days_until_friday = max(4 - local_now.weekday(), 0)
            start = (local_now + timedelta(days=days_until_friday)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=7 - start.weekday())
            events = events.filter(start_at__gte=max(now, start), start_at__lt=end)
        elif when == 'month':
            next_month = (local_now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            events = events.filter(start_at__lt=next_month)

    events = events.order_by('-created_at', 'pk') if sort == 'newest' else events.order_by('-start_at' if when == 'past' else 'start_at', 'pk')
    page = Paginator(events, 12).get_page(request.GET.get('page'))

    upcoming = published.filter(start_at__gte=now)
    next_event = upcoming.filter(is_featured=True).first() or upcoming.first()
    cities = (
        Event.objects.filter(is_published=True)
        .order_by('city')
        .values_list('city', flat=True)
        .distinct()
    )

    context = {
        'events': page,
        'page_obj': page,
        'result_count': page.paginator.count,
        'next_event': next_event,
        'categories': EventCategory.choices,
        'cities': cities,
        'query': query,
        'selected_category': category,
        'selected_city': city,
        'selected_when': when,
        'selected_sort': sort,
    }
    # Keep all active filters when switching category or navigating pages.
    params = request.GET.copy()
    params.pop('page', None)
    context['filter_query'] = params.urlencode()
    context['category_links'] = []
    for value, label in [('', 'All experiences'), *EventCategory.choices]:
        category_params = params.copy()
        category_params['category'] = value
        context['category_links'].append({'value': value, 'label': label, 'url': '?' + category_params.urlencode() + '#events'})
    return render(request, 'events/list.html', context)


def event_detail(request, slug):
    from apps.payments.availability import available_methods
    methods = available_methods()
    event = get_object_or_404(
        Event.objects.prefetch_related('ticket_types', 'gallery', 'lineup'), slug=slug, is_published=True
    )
    ticket_types = [t for t in event.ticket_types.all() if t.is_active]
    related = (
        Event.objects.filter(is_published=True, category=event.category, start_at__gte=timezone.now())
        .exclude(pk=event.pk).prefetch_related('ticket_types')[:3]
    )
    ticket_types_data = [
        {
            'id': t.id,
            'name': t.name,
            'description': t.description,
            'price': float(t.price),
            'remaining': t.remaining,
            'max_per_order': t.max_per_order,
            'sales_closed': bool(t.sales_end and t.sales_end <= timezone.now()),
            'waitlist_url': reverse('tickets:join_waitlist', args=[t.pk]),
        }
        for t in ticket_types
    ]
    return render(
        request,
        'events/detail.html',
        {
            'event': event,
            'ticket_types': ticket_types,
            'ticket_types_data': ticket_types_data,
            'related_events': related,
            'gallery': event.gallery.all(),
            'lineup': event.lineup.all(),
            'event_json_ld': event_json_ld(event, ticket_types, request),
            'now': timezone.now(),
            'event_image_url': request.build_absolute_uri(event.cover_image.url) if event.cover_image else '',
            'checkout_data': {
                'types': ticket_types_data,
                'checkoutUrl': reverse('tickets:checkout', args=[event.slug]),
                'csrfToken': get_token(request),
                'eventTitle': event.title,
                'eventDate': timezone.localtime(event.start_at).strftime('%a, %d %b %Y · %I:%M %p'),
                'eventVenue': f'{event.venue}, {event.city}',
                'paystackEnabled': 'paystack' in methods,
                'mpesaEnabled': 'mpesa' in methods,
                'authenticated': request.user.is_authenticated,
                'buyerName': request.user.get_full_name() if request.user.is_authenticated else '',
                'buyerEmail': request.user.email if request.user.is_authenticated else '',
                'termsUrl': reverse('terms'),
                'privacyUrl': reverse('privacy'),
            },
        },
    )
