from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    # The trailing <token> must match settings.MPESA_CALLBACK_TOKEN — Safaricom's webhook
    # has no other authentication, so this keeps the endpoint from being a bare public URL.
    path('mpesa/callback/<str:token>/', views.mpesa_callback, name='mpesa_callback'),
    path('stripe/webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('paystack/webhook/', views.paystack_webhook, name='paystack_webhook'),
    path('status/<str:reference>/', views.payment_status, name='status'),
]
