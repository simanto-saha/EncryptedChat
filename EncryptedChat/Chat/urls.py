from django.urls import path
from . import views

urlpatterns = [
    path('', views.view_details, name='index'),
    path('api/register/', views.user_register, name='user_register'),
    path('api/login/', views.user_login, name='user_login'),
    path('api/logout/', views.user_logout, name='user_logout'),
]