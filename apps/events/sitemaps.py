from django.contrib.sitemaps import Sitemap

from .models import Event


class EventSitemap(Sitemap):
    changefreq = 'daily'

    def items(self):
        return Event.objects.filter(is_published=True)

    def lastmod(self, event):
        return event.updated_at

    def priority(self, event):
        return 0.8 if event.is_featured else 0.5


class StaticViewSitemap(Sitemap):
    priority = 0.6
    changefreq = 'daily'

    def items(self):
        return ['events:list', 'tickets:my_tickets']

    def location(self, name):
        from django.urls import reverse
        return reverse(name)
