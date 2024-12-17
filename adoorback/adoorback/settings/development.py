# import sentry_sdk
# from sentry_sdk.integrations.django import DjangoIntegration
from .base import *

DEBUG = True

BASE_URL = 'http://localhost:8000'

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }
#
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'diivers',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': os.environ.get('DB_HOST', 'localhost'),  # 환경변수 없으면 localhost 사용
        'POST': '',
    },
}

# sentry_sdk.init(
#     dsn="https://3525cb8e094e49fe9973fd92ccbf456b@o486285.ingest.sentry.io/5543025",
#     integrations=[DjangoIntegration()],
#     traces_sample_rate=1.0,

#     send_default_pii=True
# )

ALLOWED_HOSTS = ['ec2-3-39-220-146.ap-northeast-2.compute.amazonaws.com', 'localhost', "127.0.0.1"]

CORS_ALLOWED_ORIGINS = ['http://localhost:3000']
CSRF_TRUSTED_ORIGINS = ['http://localhost:3000']
CORS_ALLOW_CREDENTIALS = True

FRONTEND_URL = 'http://localhost:3000'
