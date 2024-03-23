# chat/urls.py
from django.urls import path

from . import views


urlpatterns = [
    path('rooms/', views.ChatRoomList.as_view()),
    path('rooms/<int:pk>/', views.ChatRoomFriendList.as_view()),
    path('<int:pk>/messages/', views.ChatMessagesListView.as_view()),
    path('rooms/one_on_one/<int:pk>/', views.OneOnOneChatRoomId.as_view()),
]
