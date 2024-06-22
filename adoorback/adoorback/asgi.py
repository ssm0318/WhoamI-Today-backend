"""
ASGI config for adoorback project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/howto/deployment/asgi/
"""
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.security.websocket import AllowedHostsOriginValidator
from .middleware import JwtAuthMiddlewareStack
from chat.routing import websocket_urlpatterns


application = ProtocolTypeRouter(
    {   
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JwtAuthMiddlewareStack(
                URLRouter(
                    websocket_urlpatterns
                )   
            ),  
        ),  
    }   
)
