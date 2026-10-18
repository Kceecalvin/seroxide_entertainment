from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class EventCategory(models.TextChoices):
    CONCERT = 'concert', 'Concert'
    FESTIVAL = 'festival', 'Festival'
    NIGHTLIFE = 'nightlife', 'Nightlife & Club'
    COMEDY = 'comedy', 'Comedy'
    THEATRE = 'theatre', 'Theatre & Arts'
    SPORTS = 'sports', 'Sports'
    CONFERENCE = 'conference', 'Conference'
    OTHER = 'other', 'Other'


class Event(models.Model):
    class Theme(models.TextChoices):
        CLASSIC = 'classic', 'SeroTix signature'
        AFTER_DARK = 'after-dark', 'After Dark'
        COASTAL = 'coastal', 'Coastal'
        GOLD_NIGHT = 'gold-night', 'Gold Night'
        ELECTRIC = 'electric', 'Electric'

    theme = models.CharField(max_length=16, choices=Theme.choices, default=Theme.CLASSIC)

    class ReviewStatus(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING = 'pending', 'In review'
        APPROVED = 'approved', 'Approved'
        CHANGES = 'changes', 'Changes requested'

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='seller_events')
    review_status = models.CharField(max_length=12, choices=ReviewStatus.choices, default=ReviewStatus.APPROVED)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.CharField(max_length=20, choices=EventCategory.choices, default=EventCategory.OTHER)
    description = models.TextField()
    organizer_name = models.CharField(max_length=150, default='SeroTix')

    venue = models.CharField(max_length=200)
    city = models.CharField(max_length=100, default='Nairobi')
    address = models.CharField(max_length=255, blank=True)

    start_at = models.DateTimeField()
    end_at = models.DateTimeField(blank=True, null=True)

    cover_image = models.ImageField(upload_to='events/covers/', blank=True, null=True)

    is_published = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_at']
        indexes = [
            models.Index(fields=['start_at']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.owner_id and self.review_status != self.ReviewStatus.APPROVED:
            self.is_published = False
            if kwargs.get('update_fields'):
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'is_published'}
        if not self.slug:
            base_slug = slugify(self.title)[:200]
            slug = base_slug
            n = 1
            while Event.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                n += 1
                slug = f'{base_slug}-{n}'
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('events:detail', kwargs={'slug': self.slug})

    @property
    def is_past(self):
        end = self.end_at or self.start_at
        return end < timezone.now()

    @property
    def is_sold_out(self):
        types = self.available_ticket_types
        if not types:
            return False
        return all(t.remaining <= 0 for t in types)

    @property
    def min_price(self):
        active = self.available_ticket_types
        in_stock = [t for t in active if t.remaining > 0]
        prices = [t.price for t in (in_stock or active)]
        return min(prices) if prices else None

    @property
    def total_remaining(self):
        return sum(t.remaining for t in self.available_ticket_types)

    @property
    def available_ticket_types(self):
        # Filtering in Python reuses prefetch_related instead of issuing a query
        # for each price and availability label in the event grid.
        now = timezone.now()
        return [t for t in self.ticket_types.all() if t.is_active and (not t.sales_end or t.sales_end > now)]


class EventImage(models.Model):
    """A gallery photo for an event, beyond its single cover image."""
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='gallery')
    image = models.ImageField(upload_to='events/gallery/')
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.event.title} — gallery photo {self.pk}'


class LineupItem(models.Model):
    """A performer, speaker, or schedule slot for an event."""
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='lineup')
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=150, blank=True, help_text='e.g. "Headliner", "Opening act", "MC"')
    time = models.CharField(max_length=50, blank=True, help_text='Free text, e.g. "9:00 PM"')
    photo = models.ImageField(upload_to='events/lineup/', blank=True, null=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.name} — {self.event.title}'


class EventReview(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='reviews')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=12, choices=Event.ReviewStatus.choices)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
