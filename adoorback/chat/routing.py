# chat/routing.py
from django.urls import path, re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/chat/(?P<room_id>\d+)/$", consumers.ChatConsumer.as_asgi()),
    re_path(r"ws/chat/chat_list/$", consumers.ChatRoomListConsumer.as_asgi()),
    re_path(r"ws/chat/friend_list/$", consumers.FriendListConsumer.as_asgi()),
    re_path(r"ws/chat/icon_badge/$", consumers.ChatIconConsumer.as_asgi()),
]