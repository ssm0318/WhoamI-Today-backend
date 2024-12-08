from django.urls import path
from . import views


urlpatterns = [
    path('user/<int:pk>/', views.PingList.as_view(), name='ping_list'),
    path('<int:pk>/mark-as-read/', views.MarkPingAsRead.as_view(), name='mark-ping-as-read'),
]
