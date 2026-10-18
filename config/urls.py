from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.views.generic import TemplateView

from apps.core.views import contact, health_check
from apps.events.sitemaps import EventSitemap, StaticViewSitemap

# Only the owner can use Django's unrestricted administration surface.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser

sitemaps = {
    'events': EventSitemap,
    'pages': StaticViewSitemap,
}

urlpatterns = [
    # Admin Panel (The secure backbone for event management)
    path('secure-admin-panel/', admin.site.urls), # Use a custom URL for security

    # Branded organizer dashboard — day-to-day event & pricing management (staff-only)
    path('manage/', include('apps.dashboard.urls')),

    # Buyer accounts — signup/login/My Account (guest checkout remains fully supported)
    path('account/', include('apps.accounts.urls')),

    path('contact/', contact, name='contact'),
    path('healthz/', health_check, name='health_check'),

    # Legal — Privacy Policy / Terms of Service
    path('privacy/', TemplateView.as_view(template_name='legal/privacy.html'), name='privacy'),
    path('terms/', TemplateView.as_view(template_name='legal/terms.html'), name='terms'),

    # SEO: search engine discovery
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),

    # Public-facing App URLs
    path('', include('apps.events.urls')), # The main marketing/event listing page
    path('tickets/', include('apps.tickets.urls')), # Ticket booking process
    path('payments/', include('apps.payments.urls')), # Payment callbacks and status checks
]

# Add media and static handling for development ONLY
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if getattr(settings, 'LOCAL_DEMO_ENABLED', False) and settings.DEBUG:
    from apps.accounts import demo
    urlpatterns += [
        path('demo/', demo.hub, name='demo_hub'),
        path('demo/switch/<str:key>/', demo.switch, name='demo_switch'),
        path('demo/email/<int:pk>/', demo.email_preview, name='demo_email'),
    ]
