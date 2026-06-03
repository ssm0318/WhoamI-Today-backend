# import sentry_sdk
# from sentry_sdk.integrations.django import DjangoIntegration
from .base import *

DEBUG = False

# BASE_URL = 'https://whoami.gina-park.site'
BASE_URL = 'https://whoami-test-group.gina-park.site'

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'whoamitoday'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 600,
    },
}

# sentry_sdk.init(
#     dsn="https://3525cb8e094e49fe9973fd92ccbf456b@o486285.ingest.sentry.io/5543025",
#     integrations=[DjangoIntegration()],
#     traces_sample_rate=0.2,

#     send_default_pii=True
# )

# CORS_ALLOW_CREDENTIALS = True

# SESSION_COOKIE_SECURE = True
# SESSION_COOKIE_SAMESITE = 'None'

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'

# CSRF_TRUSTED_ORIGINS = [
#    "develop.d3t1tnno5uz3sa.amplifyapp.com",
#    "localhost"
# ]
CSRF_TRUSTED_ORIGINS = [
    'https://whoami.gina-park.site',    
    "https://*.gina-park.site",
    'https://jaewonkim.me',
    'https://www.jaewonkim.me',
    'https://ssm0318.github.io',
    'http://localhost:4178',
    'http://127.0.0.1:4178',
]

ALLOWED_HOSTS = [
    'ec2-43-203-123-225.ap-northeast-2.compute.amazonaws.com',
    'localhost',
    '127.0.0.1',
    '43.203.123.225',
    'ip-172-31-12-68',
    '.gina-park.site',
    r".*\.gina-park\.site", 
]

CORS_ALLOWED_ORIGINS = [
    "https://ec2-43-203-123-225.ap-northeast-2.compute.amazonaws.com",  # Public DNS name
    "https://43.203.123.225",
    "https://jaewonkim.me",
    "https://www.jaewonkim.me",
    "https://ssm0318.github.io",
    "http://localhost:4178",
    "http://127.0.0.1:4178",
]

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.gina-park\.site$"
]

# FRONTEND_URL = 'https://whoami.gina-park.site'
FRONTEND_URL = 'https://whoami-test-group.gina-park.site'

# Redis for WebSocket channel layer (docker service name = redis)
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# Production logging: reduce disk I/O by raising log levels
# base.py의 DEBUG 레벨은 개발 환경용으로 유지하고, 프로덕션에서만 오버라이드
LOGGING['loggers']['django']['level'] = 'WARNING'
LOGGING['loggers']['adoorback']['level'] = 'INFO'
