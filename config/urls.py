from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Admin Panel (The secure backbone for event management)
    path('secure-admin-panel/', admin.site.urls), # Use a custom URL for security

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