from rest_framework_simplejwt.authentication import JWTAuthentication
from adoorback.filters import set_current_request


class LoggingJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            set_current_request(request)
        return result
