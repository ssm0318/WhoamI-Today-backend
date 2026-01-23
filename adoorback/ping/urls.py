from django.urls import path
from . import views


urlpatterns = [
    path('rooms/', views.PingRoomList.as_view(), name='ping-room-list'),
    path('user/<int:pk>/', views.PingList.as_view(), name='ping_list'),
]
