import json

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.generic.http import AsyncHttpConsumer
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections
from jwt import decode as jwt_decode
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken
from urllib.parse import parse_qs


User = get_user_model()

@database_sync_to_async
def get_user(validated_token):
    try:
        return User.objects.get(id=validated_token["user_id"])
    except User.DoesNotExist:
        return AnonymousUser()


class JwtAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        # close old database connections to prevent usage of timed out connections
        close_old_connections()

        try:
            token = parse_qs(scope["query_string"].decode("utf8"))["token"][0]
        except KeyError:
            print("No token provided")
            await self.send_error_response(send, "No token provided")
            return
        # authenticate
        try:
            # validate the token, raise an error if invalid
            UntypedToken(token)
        except (InvalidToken, TokenError) as e:
            print(e, "Invalid token provided")
            await self.send_error_response(send, "Invalid token provided")
            return
        else:
            decoded_data = jwt_decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            scope["user"] = await get_user(validated_token=decoded_data)

            if isinstance(scope["user"], AnonymousUser):
                print(e, "You must be logged in to connect")
                await self.send_error_response(send, "You must be logged in to connect")
                return
        return await super().__call__(scope, receive, send)

    async def send_error_response(self, send, message):
        response = {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
            ],
        }
        await send(response)
        await send({
            "type": "http.response.body",
            "body": json.dumps({"error": message}).encode()
        })

def JwtAuthMiddlewareStack(inner):
    return JwtAuthMiddleware(AuthMiddlewareStack(inner))
