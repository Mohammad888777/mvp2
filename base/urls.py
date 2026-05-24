# core/urls.py
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('mapping/<str:session_id>/', views.mapping_page, name='mapping_page'),

    path('history/', views.history_page, name='history_page'),



    path('api/login', views.api_login, name='api_login'),
    path('api/guest', views.guest_login, name='guest_login'),
    path('api/me', views.me, name='me'),
    path('api/logout', views.logout, name='logout'),
    path('api/upload', views.upload_file, name='upload'),
    path('api/process', views.process_data, name='process'),
    path('api/download-cleaned/<str:session_id>', views.download_cleaned, name='download_cleaned'),


    path('api/history', views.get_history, name='get_history'),



    path('health', views.health, name='health'),
]