# chat/urls.py
from django.urls import path

from . import views


<<<<<<< HEAD
urlpatterns = [
    path('rooms/', views.ChatRoomList.as_view()),
    path('rooms/<int:pk>/', views.ChatRoomFriendList.as_view()),
    path('<int:pk>/messages/', views.ChatMessagesListView.as_view()),
]
=======
urlpatterns = []
>>>>>>> 942c1c5 (feat: basic settings for chat)
