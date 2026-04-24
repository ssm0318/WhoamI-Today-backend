import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer


class ChatListConsumer(WebsocketConsumer):
    """Per-user WebSocket for chat list updates (new messages in any conversation)."""

    def connect(self):
        user = self.scope["user"]
        self.group_id = f"user_{user.id}_chat_list"

        async_to_sync(self.channel_layer.group_add)(
            self.group_id, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_id, self.channel_name
        )

    def chat_list_update(self, event):
        """Forward chat list update to WebSocket client."""
        self.send(text_data=json.dumps(event["data"]))


class GroupChatConsumer(WebsocketConsumer):
    """WebSocket consumer for group chat rooms."""

    def connect(self):
        from chat.models import ChatRoom
        user = self.scope["user"]
        room_id = int(self.scope["url_route"]["kwargs"]["room_id"])

        try:
            room = ChatRoom.objects.get(id=room_id, is_group=True)
            if not room.members.filter(id=user.id).exists():
                self.close()
                return
        except ChatRoom.DoesNotExist:
            self.close()
            return

        self.room_group_id = f"chat_group_{room_id}"
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_id, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        if hasattr(self, 'room_group_id'):
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_id, self.channel_name
            )

    def receive(self, text_data):
        data = json.loads(text_data)
        if data.get("action") == "typing":
            user = self.scope["user"]
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_id,
                {
                    "type": "chat.typing",
                    "data": {
                        "action": "typing",
                        "user_id": user.id,
                        "username": user.username,
                    },
                },
            )

    def chat_message(self, event):
        self.send(text_data=json.dumps(event["data"]))

    def chat_reaction(self, event):
        self.send(text_data=json.dumps(event["data"]))

    def chat_typing(self, event):
        user = self.scope["user"]
        if event["data"]["user_id"] != user.id:
            self.send(text_data=json.dumps(event["data"]))


class ChatConsumer(WebsocketConsumer):
    """WebSocket consumer for real-time chat message and reaction delivery."""

    def connect(self):
        from chat.models import ChatRoom

        user = self.scope["user"]
        other_user_id = int(self.scope["url_route"]["kwargs"]["user_id"])

        ids = sorted([user.id, other_user_id])

        if user.id not in ids:
            self.close()
            return

        if not ChatRoom.objects.filter(
            user1_id=ids[0], user2_id=ids[1], is_group=False
        ).exists():
            self.close()
            return

        self.room_group_id = f"chat_{ids[0]}_{ids[1]}"

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_id, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        if hasattr(self, 'room_group_id'):
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_id, self.channel_name
            )

    def receive(self, text_data):
        """Handle incoming WebSocket messages (typing events)."""
        data = json.loads(text_data)
        if data.get("action") == "typing":
            user = self.scope["user"]
            other_user_id = int(self.scope["url_route"]["kwargs"]["user_id"])

            # Broadcast to the chat room (for in-chat indicator)
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_id,
                {
                    "type": "chat.typing",
                    "data": {
                        "action": "typing",
                        "user_id": user.id,
                        "username": user.username,
                    },
                },
            )

            # Broadcast to the other user's chat list (for list page indicator)
            async_to_sync(self.channel_layer.group_send)(
                f"user_{other_user_id}_chat_list",
                {
                    "type": "chat.list.update",
                    "data": {
                        "action": "typing",
                        "opponent_id": user.id,
                        "username": user.username,
                    },
                },
            )

    def chat_message(self, event):
        """Forward new message broadcast to WebSocket client."""
        self.send(text_data=json.dumps(event["data"]))

    def chat_reaction(self, event):
        """Forward reaction broadcast to WebSocket client."""
        self.send(text_data=json.dumps(event["data"]))

    def chat_typing(self, event):
        """Forward typing indicator — skip sending to the typer themselves."""
        user = self.scope["user"]
        if event["data"]["user_id"] != user.id:
            self.send(text_data=json.dumps(event["data"]))

    def friendship_broken(self, event):
        """Notify both sides that the friendship between the chat participants was broken."""
        self.send(text_data=json.dumps(event["data"]))
