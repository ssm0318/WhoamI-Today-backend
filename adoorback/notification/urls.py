from django.urls import path

from notification import views

urlpatterns = [
    path('', views.NotificationList.as_view(), name='notification-list'),
    path('friend-requests/', views.FriendRequestNotiList.as_view(), name='friend-request-noti-list'),
    path('response-requests/', views.ResponseRequestNotiList.as_view(), name='response-request-noti-list'),
    path(r'unread/', views.notification_id, name='notification-id'),
    path('read/', views.NotificationDetail.as_view(), name='notification-read'),
]
