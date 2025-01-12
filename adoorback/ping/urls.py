from django.urls import path
from . import views


urlpatterns = [
    path('user/<int:pk>/', views.PingList.as_view(), name='ping_list'),
]
