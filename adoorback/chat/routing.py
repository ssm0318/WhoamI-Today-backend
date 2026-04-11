from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/chat/list/$", consumers.ChatListConsumer.as_asgi()),
    re_path(r"ws/chat/group/(?P<room_id>\d+)/$", consumers.GroupChatConsumer.as_asgi()),
    re_path(r"ws/chat/(?P<user_id>\d+)/$", consumers.ChatConsumer.as_asgi()),
]
