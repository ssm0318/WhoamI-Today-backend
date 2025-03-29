from django.conf import settings
from rest_framework import authentication
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication
from zoneinfo import ZoneInfo
from django.utils import timezone

from adoorback.filters import set_current_request


class SessionAuthentication(authentication.SessionAuthentication):
    """
    This class is needed, because REST Framework's default SessionAuthentication does never return 401's,
    because they cannot fill the WWW-Authenticate header with a valid value in the 401 response. As a
    result, we cannot distinguish calls that are not unauthorized (401 unauthorized) and calls for which
    the user does not have permission (403 forbidden). See https://github.com/encode/django-rest-framework/issues/5968

    We do set authenticate_header function in SessionAuthentication, so that a value for the WWW-Authenticate
    header can be retrieved and the response code is automatically set to 401 in case of unauthenticated requests.
    """

    def authenticate_header(self, request):
        return 'Session'


def dummy_get_response(request):  # pragma: no cover
    return None


def enforce_csrf(request):
    check = CSRFCheck(dummy_get_response)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied('CSRF Failed: %s' % reason)


class CustomAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        
        if header is None:
            raw_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE']) or None
        else:
            raw_token = self.get_raw_token(header)
        if raw_token is None:
            timezone.deactivate()
            return None

        validated_token = self.get_validated_token(raw_token)

        # for logging
        set_current_request(request)
        enforce_csrf(request)        
        user = self.get_user(validated_token)
        if user and user.is_authenticated and user.timezone:
            timezone.activate(ZoneInfo(user.timezone))
        else:
            timezone.deactivate()
        return user, validated_token
    
    
