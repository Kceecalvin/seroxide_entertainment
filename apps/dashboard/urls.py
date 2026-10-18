from django.contrib.auth import views as auth_views
from django.urls import path

from apps.core.ratelimit import ratelimit

from . import views, operations
from apps.accounts import promotions

app_name = 'dashboard'

# 20 attempts / 10 minutes per IP — generous for a genuine typo, tight enough
# to meaningfully slow credential-stuffing / brute force against staff accounts
# (there was previously no throttling on this endpoint at all).
_login_view = ratelimit(key_prefix='dashboard-login', limit=20, window_seconds=600)(
    views.RoleAwareLoginView.as_view()
)

urlpatterns = [
    path('promotions/', promotions.enquiries, name='promotions'),
    path('promotions/<int:pk>/', promotions.update_status, name='promotion_update'),
    path('team/', operations.team, name='team'),
    path('reviews/', operations.reviews, name='reviews'),
    path('reviews/<int:pk>/', operations.review, name='review'),
    path('emails/', operations.emails, name='emails'),
    path('emails/<int:pk>/retry/', operations.retry_email, name='retry_email'),
    path('login/', _login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='dashboard:login'), name='logout'),

    path('', views.dashboard_home, name='home'),
    path('events/new/', views.event_create, name='event_create'),
    path('events/<slug:slug>/', views.event_edit, name='event_edit'),
    path('events/<slug:slug>/tickets/new/', views.ticket_type_create, name='ticket_type_create'),
    path('tickets/<int:pk>/edit/', views.ticket_type_edit, name='ticket_type_edit'),
    path('tickets/<int:pk>/toggle/', views.ticket_type_toggle, name='ticket_type_toggle'),
    path('events/<slug:slug>/gallery/new/', views.event_image_create, name='event_image_create'),
    path('gallery/<int:pk>/delete/', views.event_image_delete, name='event_image_delete'),
    path('events/<slug:slug>/lineup/new/', views.lineup_item_create, name='lineup_item_create'),
    path('lineup/<int:pk>/delete/', views.lineup_item_delete, name='lineup_item_delete'),
    path('events/<slug:slug>/orders/', views.event_orders, name='event_orders'),

    path('payments/reconciliation/', views.payment_reconciliation, name='payment_reconciliation'),
    path('payments/<int:pk>/retry/', views.payment_retry_fulfillment, name='payment_retry_fulfillment'),
    path('payments/<int:pk>/refund/', views.issue_refund_view, name='issue_refund'),
]
