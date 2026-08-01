from django.urls import path
from . import views

urlpatterns = [
    path('me', views.me),
    path('login', views.login_view),
    path('logout', views.logout_view),
]
