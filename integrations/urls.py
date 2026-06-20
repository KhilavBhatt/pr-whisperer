from django.urls import path
from . import views

urlpatterns = [
    path('github/login/', views.github_login, name='github-login'),
    path('github/callback/', views.github_callback, name='github-callback'),
    path('me/', views.me, name='me'),
]
