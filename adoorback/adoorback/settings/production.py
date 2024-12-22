# import sentry_sdk
# from sentry_sdk.integrations.django import DjangoIntegration
from .base import *

DEBUG = False

BASE_URL = 'https://whoami.gina-park.site'

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'whoamitoday',
        'USER': 'postgres',
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
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

#CSRF_COOKIE_SECURE = True
#CSRF_COOKIE_SAMESITE = 'None'

# CSRF_TRUSTED_ORIGINS = [
#    "develop.d3t1tnno5uz3sa.amplifyapp.com",
#    "localhost"
# ]
CSRF_TRUSTED_ORIGINS = ['https://whoami.gina-park.site']


ALLOWED_HOSTS = ['ec2-43-203-123-225.ap-northeast-2.compute.amazonaws.com', 'localhost', '43.203.123.225', 'ip-172-31-12-68']

CORS_ALLOWED_ORIGINS = [
#    "https://develop.d3t1tnno5uz3sa.amplifyapp.com",
#    "http://localhost:3000",
    "https://ec2-43-203-123-225.ap-northeast-2.compute.amazonaws.com",  # Public DNS 이름
    "https://43.203.123.225",  # Public IP 주소
]

FRONTEND_URL = 'https://whoami.gina-park.site'
