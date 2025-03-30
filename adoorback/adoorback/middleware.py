import json

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.generic.http import AsyncHttpConsumer
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections, DatabaseError
from django.utils import translation
from jwt import decode as jwt_decode
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken
from urllib.parse import parse_qs

from custom_fcm.models import CustomFCMDevice

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


class CustomLocaleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def _get_language_from_fcm_device(self, user):
        """Get language from user's active FCM device."""
        try:
            device = CustomFCMDevice.objects.filter(user=user, active=True).first()
            if device and device.language:
                return device.language if device.language in dict(settings.LANGUAGES) else None
        except DatabaseError:
            return None
        return None

    def _get_language_from_header(self, request):
        """Parse and validate language from HTTP_ACCEPT_LANGUAGE header."""
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        if accept_language:
            lang = accept_language.split(',')[0].split('-')[0].strip().lower()
            return lang if lang in dict(settings.LANGUAGES) else None
        return None

    def _get_language_for_request(self, request):
        """Determine the appropriate language for the request."""
        # Special handling for FCM device registration
        if request.path.startswith('/api/devices/'):
            return self._get_language_from_header(request) or settings.LANGUAGE_CODE

        # For authenticated users, try FCM device language first
        if hasattr(request, 'user') and request.user.is_authenticated:
            fcm_lang = self._get_language_from_fcm_device(request.user)
            if fcm_lang:
                return fcm_lang

        # Try HTTP_ACCEPT_LANGUAGE header
        header_lang = self._get_language_from_header(request)
        if header_lang:
            return header_lang

        # Fall back to default language
        return settings.LANGUAGE_CODE

    def __call__(self, request):
        # Skip language handling for ASGI requests
        if hasattr(request, 'scope') and request.scope.get('type') == 'http':
            # Get the appropriate language
            lang = self._get_language_for_request(request)

            # Use translation.override() to ensure language persists throughout the request
            with translation.override(lang):
                response = self.get_response(request)

                # Set language cookie if it's different from current
                if not request.COOKIES.get('django_language') == lang:
                    response.set_cookie(
                        settings.LANGUAGE_COOKIE_NAME,
                        lang,
                        max_age=settings.LANGUAGE_COOKIE_AGE,
                        path=settings.LANGUAGE_COOKIE_PATH,
                        domain=settings.LANGUAGE_COOKIE_DOMAIN,
                        secure=settings.LANGUAGE_COOKIE_SECURE,
                        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
                        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
                    )

                return response

        return self.get_response(request)
