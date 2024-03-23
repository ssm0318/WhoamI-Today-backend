from datetime import datetime
import json

from asgiref.sync import async_to_sync
from channels.exceptions import DenyConnection
from channels.generic.websocket import WebsocketConsumer
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from safedelete.models import HARD_DELETE

from chat.models import Message, ChatRoom, MessageLike
from utils.helpers import update_last_read_message


TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.000+00:00"

from chat.models import Message, ChatRoom, UserChatActivity
from utils.helpers import update_last_read_message


User = get_user_model()


class ChatConsumer(WebsocketConsumer):
    def connect(self):
        user = self.scope["user"]
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_id = f"chat_{self.room_id}"

        chat_room = ChatRoom.objects.get(id=self.room_id)
        if user not in chat_room.users.all():
            raise DenyConnection("You must be a member to join this chat.")

        # Join room group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_id, self.channel_name
        )

        self.accept()

        # Update last read message for user
        user = self.scope["user"]
        chat_room = ChatRoom.objects.get(id=self.room_id)
        update_last_read_message(user, chat_room)

        # Send message to own chat_list group 
        # (in case of accessing chatroom, chat list in different devices)
        if chat_room.messages.all():
            async_to_sync(self.channel_layer.group_send)(
                f"user_{user.id}_chat_list", {
                    "type": "chat.message",
                    "roomId": self.room_id,
                    "content": chat_room.last_message_content,
                    "timestamp": chat_room.last_message_time.strftime(TIME_FORMAT),
                    "unreadCnt": 0
                }
            )

        # Send message to own friend_list group 
        # (in case of accessing chatroom, friend list in different devices)
        if chat_room.messages.all() and chat_room.users.count() == 2:
            friend_id = chat_room.users.exclude(id=user.id).first().id
            async_to_sync(self.channel_layer.group_send)(
                f"user_{user.id}_friend_list", {
                    "type": "chat.message",
                    "friendId": friend_id,
                    "unreadCnt": 0
                }
            )

        # Send message to own chat_icon group 
        # (in case of accessing chatroom, app in different devices)
        if chat_room.messages.all():
            updated_cnt = user.unread_message_cnt
            async_to_sync(self.channel_layer.group_send)(
                f"user_{user.id}_chat_icon", {
                    "type": "chat.message",
                    "unreadCnt": updated_cnt
                }
            )

    def disconnect(self, close_code):
        # Leave room group
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_id, self.channel_name
        )

    # Receive message from WebSocket
    def receive(self, text_data):
        text_data_json = json.loads(text_data)

        if text_data_json.get('action') == 'like':
            user_id = self.scope["user"].id
            message_id = text_data_json["messageId"]

            # Save like to database
            MessageLike.objects.create(user_id=user_id, message_id=message_id)

            # Send like to room group
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_id, {
                    "type": "chat.like",
                    "messageId": message_id,
                }
            )

        elif text_data_json.get('action') == 'remove_like':
            user_id = self.scope["user"].id
            message_like_id = text_data_json["messageLikeId"]

            # Destroy like in database
            message_like = MessageLike.objects.get(id=message_like_id)
            if message_like.user_id != user_id:
                raise PermissionDenied("You can only remove likes that you created.")
            message_id = message_like.message_id
            message_like.delete(force_policy=HARD_DELETE)

            # Send like remove to room group
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_id, {
                    "type": "chat.like",
                    "messageId": message_id,
                }
            )

        elif text_data_json.get('action') == 'message':
            content = text_data_json["content"]
            user_id = text_data_json["userId"]
            user_name = text_data_json["userName"]
            parent_id = text_data_json["parentId"]
            timestamp = datetime.utcnow()
            timestamp_str = timestamp.strftime(TIME_FORMAT)

            # validation
            parent, parent_content = None, None
            if parent_id is not None:
                try:
                    parent = Message.objects.get(id=parent_id)
                    parent_content = parent.content
                except Message.DoesNotExist:
                    raise ValidationError("Parent message does not exist.")

            # Save message to database
            new_message = Message.objects.create(
                sender_id=user_id, 
                content=content, 
                chat_room_id=self.room_id, 
                timestamp=timestamp,
                parent=parent
            )
            message_id = new_message.id

            # Send message to room group
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_id, {
                    "type": "chat.message", 
                    "content": content, 
                    "messageId": message_id,
                    "userName": user_name, 
                    "timestamp": timestamp_str,
                    "parentId": parent_id,
                    "parentContent": parent_content
                }
            )

            # Send message to chat_list, chat_icon group
            chat_room = ChatRoom.objects.get(id=self.room_id)
            recipients = chat_room.users.exclude(id=user_id)
            for r in recipients:
                async_to_sync(self.channel_layer.group_send)(
                    f"user_{r.id}_chat_list", {
                        "type": "chat.message",
                        "roomId": self.room_id,
                        "content": content,
                        "timestamp": timestamp_str,
                        "unreadCnt": chat_room.unread_cnt(r)
                    }
                )
                updated_cnt = r.unread_message_cnt
                async_to_sync(self.channel_layer.group_send)(
                    f"user_{r.id}_chat_icon", {
                        "type": "chat.message",
                        "unreadCnt": updated_cnt
                    }
                )

            # Send message to friend_list group
            if chat_room.users.count() == 2:
                friend_id = recipients.first().id
                async_to_sync(self.channel_layer.group_send)(
                    f"user_{friend_id}_friend_list", {
                        "type": "chat.message",
                        "friendId": user_id,
                        "unreadCnt": chat_room.unread_cnt(r)
                    }
                )

    # Receive message from room group
    def chat_message(self, event):
        content = event["content"]
        user_name = event["userName"]
        timestamp = event["timestamp"]
        parent_id = event["parentId"]
        parent_content = event["parentContent"]

        # Send message to WebSocket
        self.send(text_data=json.dumps({
            "content": content, 
            "userName": user_name, 
            "timestamp": timestamp,
            "parentId": parent_id,
            "parentContent": parent_content
        }))

        # Save read status to database
        user = self.scope["user"]
        chat_room = ChatRoom.objects.get(id=self.room_id)
        if user.username != user_name:
            update_last_read_message(user, chat_room)

        # Send message to own chat_list group 
        # (in case of accessing chatroom, chat list in different devices)
        if chat_room.messages.all():
            async_to_sync(self.channel_layer.group_send)(
                f"user_{user.id}_chat_list", {
                    "type": "chat.message",
                    "roomId": self.room_id,
                    "content": chat_room.last_message_content,
                    "timestamp": chat_room.last_message_time.strftime(TIME_FORMAT),
                    "unreadCnt": 0
                }
            )

        # Send message to own friend_list group 
        # (in case of accessing chatroom, friend list in different devices)
        if chat_room.messages.all() and chat_room.users.count() == 2:
            friend_id = chat_room.users.exclude(id=user.id).first().id
            async_to_sync(self.channel_layer.group_send)(
                f"user_{user.id}_friend_list", {
                    "type": "chat.message",
                    "friendId": friend_id,
                    "unreadCnt": 0
                }
            )

    # Receive like change from room group
    def chat_like(self, event):
        message_id = event["messageId"]

        message_like_cnt = Message.objects.get(id=message_id).message_likes.count()
        user = self.scope["user"]
        current_user_message_like = MessageLike.objects.filter(user_id=user.id, message_id=message_id)
        current_user_message_like_id = current_user_message_like[0].id if current_user_message_like else None

        # Send like change to WebSocket
        self.send(text_data=json.dumps({
            "action": "like",
            "messageId": message_id,
            "messageLikeCnt": message_like_cnt,
            "currentUserMessageLikeId": current_user_message_like_id
        }))

        # Send message to own chat_icon group 
        # (in case of accessing chatroom, app in different devices)
        if chat_room.messages.all():
            updated_cnt = user.unread_message_cnt
            async_to_sync(self.channel_layer.group_send)(
                f"user_{user.id}_chat_icon", {
                    "type": "chat.message",
                    "unreadCnt": updated_cnt
                }
            )


class ChatRoomListConsumer(WebsocketConsumer):
    def connect(self):
        # Make group for each user
        self.user_id = self.scope["user"].id
        self.user_group_id = f"user_{self.user_id}_chat_list"

        async_to_sync(self.channel_layer.group_add)(
            self.user_group_id, self.channel_name
        )

        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.user_group_id, self.channel_name
        )

    # Receive message from room group
    def chat_message(self, event):
        content = event["content"]
        room_id = event["roomId"]
        timestamp = event["timestamp"]
        unread_cnt = event["unreadCnt"]

        # Send message to WebSocket
        self.send(text_data=json.dumps({
            "content": content, "roomId": room_id, "timestamp": timestamp, "unreadCnt": unread_cnt
        }))


class FriendListConsumer(WebsocketConsumer):
    def connect(self):
        # Make group for each user
        self.user_id = self.scope["user"].id
        self.user_group_id = f"user_{self.user_id}_friend_list"

        async_to_sync(self.channel_layer.group_add)(
            self.user_group_id, self.channel_name
        )

        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.user_group_id, self.channel_name
        )

    # Receive message from room group
    def chat_message(self, event):
        friend_id = event["friendId"]
        unread_cnt = event["unreadCnt"]

        # Send message to WebSocket
        self.send(text_data=json.dumps({
            "friendId": friend_id, "unreadCnt": unread_cnt
        }))


class ChatIconConsumer(WebsocketConsumer):
    def connect(self):
        # Make group for each user
        self.user_id = self.scope["user"].id
        self.user_group_id = f"user_{self.user_id}_chat_icon"

        async_to_sync(self.channel_layer.group_add)(
            self.user_group_id, self.channel_name
        )

        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.user_group_id, self.channel_name
        )

    # Receive message from room group
    def chat_message(self, event):
        unread_cnt = event["unreadCnt"]

        # Send message to WebSocket
        self.send(text_data=json.dumps({
            "unreadCnt": unread_cnt
        }))
