from django.urls import path

from . import views, gates

app_name = 'tickets'

urlpatterns = [
    path('checkout/<slug:slug>/', views.checkout, name='checkout'),
    path('waitlist/<int:ticket_type_id>/', views.join_waitlist, name='join_waitlist'),
    path('order/<str:reference>/pending/', views.order_pending, name='order_pending'),
    path('order/<str:reference>/success/', views.order_success, name='order_success'),
    path('my-tickets/', views.my_tickets, name='my_tickets'),
    path('verify/<uuid:serial>/', views.verify_ticket, name='verify'),
    path('scan/events/<int:event_id>/select/', gates.select_event, name='select_gate_event'),
    path('scan/events/<int:event_id>/', views.scanner_event, name='scanner_event'),
    path('scan/events/<int:event_id>/supervisor/', gates.supervisor, name='gate_supervisor'),
    path('scan/', views.scanner, name='scanner'),
    path('scan/api/<uuid:serial>/', views.scanner_check, name='scanner_check'),
]
