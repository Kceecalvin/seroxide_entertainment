from django.urls import path

from . import views

app_name = 'events'

urlpatterns = [
    path('discover/catalog/', views.discovery_catalog, name='catalog'),
    path('', views.event_list, name='list'),
    path('e/<slug:slug>/', views.event_detail, name='detail'),
]
