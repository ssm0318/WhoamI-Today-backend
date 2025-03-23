from rest_framework_simplejwt.authentication import JWTAuthentication
from adoorback.filters import set_current_request


class LoggingJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        print("✅ LoggingJWTAuthentication.authenticate() called")
        result = super().authenticate(request)
        if result:
            print("✅ Auth success, calling set_current_request()")
            set_current_request(request)
        else:
            print("⚠️ Auth failed or no token")
        return result
