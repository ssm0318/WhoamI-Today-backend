import contextvars
from logging import Filter
from threading import local

# 비동기 환경에서도 안전하게 동작함
_current_request = contextvars.ContextVar('current_request', default=None)

def set_current_request(request):
    _current_request.set(request)

def get_current_request():
    return _current_request.get()


class UserInfoFilter(Filter):
    def filter(self, record):
        request = get_current_request()
        print("🌀 Filter received request:", request)

        if request and hasattr(request, 'user') and request.user.is_authenticated:
            record.username = request.user.username

            # 인증 토큰 가져오기 (JWT, DRF Token 등 상황 고려)
            token = request.META.get('HTTP_AUTHORIZATION')
            if not token and hasattr(request, 'auth') and request.auth:
                token = str(request.auth)

            record.token = token if token else 'NoToken'
        else:
            record.username = 'Anonymous'
            record.token = 'NoToken'

        return True
