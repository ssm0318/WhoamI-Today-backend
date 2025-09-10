import contextvars
import json
from logging import Filter

from user_agents import parse


# Works safely in asynchronous environment
_current_request = contextvars.ContextVar('current_request', default=None)


def set_current_request(request):
    _current_request.set(request)


def get_current_request():
    return _current_request.get()


class UserInfoFilter(Filter):
    def filter(self, record):
        request = get_current_request()

        if request:
            user = getattr(request, 'user', None)

            if user and user.is_authenticated:
                record.username = getattr(user, 'username', 'Unknown')
                record.user_id = getattr(user, 'id', 'N/A')
            else:
                record.username = 'Anonymous'
                record.user_id = 'N/A'

            # Get authentication token (considering JWT, DRF Token, etc.)
            token = request.META.get('HTTP_AUTHORIZATION')
            if not token and hasattr(request, 'auth') and request.auth:
                token = str(request.auth)
            if token:
                masked_token = token[:10] + "..." + token[-5:]
            else:
                masked_token = "N/A"
            record.token = masked_token if masked_token else 'N/A'

            record.page = request.headers.get('X-Current-Page', 'N/A')

            user_agent_str = request.META.get('HTTP_USER_AGENT', '')
            user_agent = parse(user_agent_str)
            record.os = user_agent.os.family  # e.g., "iOS", "Android", "Windows"

            # request body
            try:
                if request.method in ['POST', 'PUT', 'PATCH']:
                    data = dict(request.data)  # QueryDict → dict (mutable copy)
                    # Filter sensitive information
                    sensitive_keys = ['password', 'token', 'secret', 'registration_id']
                    for key in sensitive_keys:
                        if key in data:
                            data[key] = '[FILTERED]'
                    record.body = json.dumps(data, ensure_ascii=False)
                else:
                    record.body = ''
            except Exception as e:
                record.body = f'[ERROR reading request.data: {e}]'

        else:
            record.username = 'No Request'
            record.user_id = 'N/A'
            record.token = ''
            record.page = 'N/A'
            record.body = ''
            record.os = 'N/A'

        return True
