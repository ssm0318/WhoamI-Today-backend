import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from datetime import datetime


class ChatConsumer(WebsocketConsumer):
    def connect(self):
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_id = f"chat_{self.room_id}"

        # Join room group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_id, self.channel_name
        )

        self.accept()

    def disconnect(self, close_code):
        # Leave room group
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_id, self.channel_name
        )

    # Receive message from WebSocket
    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]
        user_id = text_data_json["userId"]
        user_name = text_data_json["userName"]
        timestamp = datetime.utcnow()
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Send message to room group
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_id, {"type": "chat.message", "message": message, "userName": user_name, "timestamp": timestamp_str}
        )

        # Save message to database
        from chat.models import Message
        Message.objects.create(sender_id=user_id, content=message, chat_room_id=self.room_id, timestamp=timestamp)

        from chat.models import ChatRoom
        chat_room = ChatRoom.objects.get(id=self.room_id)
        print(chat_room)
        print(chat_room.last_message_content)
        print(chat_room.last_message_time)


    # Receive message from room group
    def chat_message(self, event):
        message = event["message"]
        user_name = event["userName"]
        timestamp = event["timestamp"]

        # Send message to WebSocket
        self.send(text_data=json.dumps({"message": message, "userName": user_name, "timestamp": timestamp}))
