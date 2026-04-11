import json
import logging
import time
import uuid

from django.urls import resolve, Resolver404
from user_agents import parse as parse_user_agent

from .route_map import ROUTE_ACTION_MAP, PATH_PREFIX_MAP

logger = logging.getLogger('experiment')

SKIP_PREFIXES = (
    '/api/health/',
    '/api/secret/',
    '/api/devices/',
    '/static/',
    '/media/',
)

SENSITIVE_KEYS = {'password', 'token', 'secret', 'registration_id'}


class ExperimentLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        if self._should_skip(path):
            return self.get_response(request)

        start = time.monotonic()
        request_id = uuid.uuid4().hex[:12]

        response = self.get_response(request)

        duration_ms = round((time.monotonic() - start) * 1000, 1)

        try:
            entry = self._build_entry(request, response, request_id, duration_ms)
            logger.info(json.dumps(entry, ensure_ascii=False, default=str))
        except Exception:
            pass

        return response

    def _should_skip(self, path):
        return any(path.startswith(p) for p in SKIP_PREFIXES)

    def _build_entry(self, request, response, request_id, duration_ms):
        user_data = self._extract_user(request)
        action_data = self._resolve_action(request)
        body = self._extract_body(request)
        client = self._extract_client(request)
        api_version = 'q' if request.path_info.startswith('/api/q/') else 'w'

        # Extract target_id from URL kwargs
        target_id = None
        try:
            resolved = resolve(request.path_info)
            target_id = resolved.kwargs.get('pk')
        except Resolver404:
            pass

        # Also try to get target info from body
        target_type = None
        if isinstance(body, dict):
            if 'target_type' in body:
                target_type = body.get('target_type')
            if 'target_id' in body and target_id is None:
                target_id = body.get('target_id')
            if 'object_id' in body and target_id is None:
                target_id = body.get('object_id')

        action = {
            'category': action_data.get('category', 'uncategorized'),
            'name': action_data.get('name', 'unknown'),
        }
        if target_id is not None:
            action['target_id'] = target_id
        if target_type is not None:
            action['target_type'] = target_type

        entry = {
            'timestamp': self._now_iso(),
            'request_id': request_id,
            'duration_ms': duration_ms,
            'user': user_data,
            'request': {
                'method': request.method,
                'path': request.path_info,
                'body': body,
            },
            'response': {
                'status_code': response.status_code,
            },
            'action': action,
            'client': client,
            'api_version': api_version,
        }
        return entry

    def _extract_user(self, request):
        user = getattr(request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            return None

        if user.is_superuser:
            user_type = 'admin'
        else:
            user_type = getattr(user, 'user_type', None)

        return {
            'id': user.id,
            'username': user.username,
            'current_ver': getattr(user, 'current_ver', None),
            'user_group': getattr(user, 'user_group', None),
            'user_type': user_type,
        }

    def _resolve_action(self, request):
        path = request.path_info
        method = request.method
        url_name = None

        try:
            resolved = resolve(path)
            url_name = resolved.url_name
        except Resolver404:
            pass

        # Check PATH_PREFIX_MAP first for conflict resolution and unnamed URLs
        for entry in PATH_PREFIX_MAP:
            if not path.startswith(entry['prefix']):
                continue
            if entry.get('skip'):
                return {'category': 'skip', 'name': 'skip'}
            # If entry specifies a url_name, only match if it matches
            if 'url_name' in entry and url_name != entry['url_name']:
                continue
            return self._resolve_action_entry(entry, method)

        # Then check ROUTE_ACTION_MAP by url_name
        if url_name and url_name in ROUTE_ACTION_MAP:
            return self._resolve_action_entry(ROUTE_ACTION_MAP[url_name], method)

        # Fallback
        path_slug = path.strip('/').replace('/', '_')
        return {
            'category': 'uncategorized',
            'name': f'{method.lower()}_{path_slug}',
        }

    def _resolve_action_entry(self, entry, method):
        category = entry.get('category', 'uncategorized')
        if 'name_by_method' in entry:
            name = entry['name_by_method'].get(method, entry.get('name', 'unknown'))
        else:
            name = entry.get('name', 'unknown')
        return {'category': category, 'name': name}

    def _extract_body(self, request):
        if request.method not in ('POST', 'PUT', 'PATCH'):
            return None

        try:
            data = request.data
            if hasattr(data, 'dict'):
                data = data.dict()
            else:
                data = dict(data)

            # Filter sensitive fields
            for key in list(data.keys()):
                if key.lower() in SENSITIVE_KEYS:
                    data[key] = '[FILTERED]'

            return data
        except Exception:
            return None

    def _extract_client(self, request):
        page = request.headers.get('X-Current-Page', None)

        os_name = None
        ua_str = request.META.get('HTTP_USER_AGENT', '')
        if ua_str:
            ua = parse_user_agent(ua_str)
            os_name = ua.os.family

        return {
            'os': os_name,
            'page': page,
        }

    def _now_iso(self):
        from django.utils import timezone
        return timezone.now().isoformat()
