from django.urls import path

from . import views

urlpatterns = [
    path('rooms/', views.ChatRoomList.as_view(), name='chat-room-list'),
    path('search/', views.MessageSearch.as_view(), name='message-search'),
    path('user/<int:pk>/', views.MessageList.as_view(), name='message-list'),
    path('<int:message_id>/reactions/', views.MessageReactionCreate.as_view(), name='message-reaction-create'),
    path('reactions/<int:pk>/', views.MessageReactionDestroy.as_view(), name='message-reaction-destroy'),
    path('user/<int:pk>/mark-read/', views.MarkMessagesRead.as_view(), name='mark-messages-read'),
    # Group chat
    path('groups/', views.GroupChatCreate.as_view(), name='group-chat-create'),
    path('groups/<int:pk>/', views.GroupChatUpdate.as_view(), name='group-chat-update'),
    path('groups/<int:pk>/leave/', views.GroupChatLeave.as_view(), name='group-chat-leave'),
    path('groups/<int:pk>/messages/', views.GroupMessageList.as_view(), name='group-message-list'),
    path('groups/<int:pk>/mark-read/', views.MarkGroupMessagesRead.as_view(), name='mark-group-messages-read'),
    # Chat requests
    path('requests/', views.ChatRequestCreate.as_view(), name='chat-request-create'),
    path('requests/sent/', views.ChatRequestSentList.as_view(), name='chat-request-sent-list'),
    path('requests/<int:pk>/respond/', views.ChatRequestUpdate.as_view(), name='chat-request-update'),
    path('requests/to/<int:requestee_id>/cancel/', views.ChatRequestCancel.as_view(), name='chat-request-cancel'),
]
