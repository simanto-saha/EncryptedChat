from django.urls import path

from . import views

urlpatterns = [
    path('', views.view_details, name='view_details'),
    path('login/', views.user_login, name='user_login'),
    path('logout/', views.user_logout, name='user_logout'),
    path('register/', views.user_register, name='user_register'),
    path('chat/', views.chat_room, name='chat_room'),
    path('api/users/', views.api_users, name='api_users'),
    path('api/messages/<int:user_id>/', views.api_messages, name='api_messages'),
    path('api/send/', views.api_send, name='api_send'),
]