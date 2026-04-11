from django.urls import path
from . import views


urlpatterns = [
    path('rooms/', views.PingRoomList.as_view(), name='ping-room-list'),
    path('user/<int:pk>/', views.PingList.as_view(), name='ping_list'),

    # Chat request system (for non-friends)
    path('requests/', views.PingRequestCreate.as_view(), name='ping-request-create'),
    path('requests/sent/', views.PingRequestSentList.as_view(), name='ping-request-sent-list'),
    path('requests/<int:pk>/respond/', views.PingRequestUpdate.as_view(), name='ping-request-update'),
]
