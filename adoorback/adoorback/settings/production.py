# import sentry_sdk
# from sentry_sdk.integrations.django import DjangoIntegration
from .base import *

DEBUG = True

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'adoor',
        'USER': 'postgres',
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': 'localhost',
        'POST': '',
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

ALLOWED_HOSTS = ['ec2-3-39-220-146.ap-northeast-2.compute.amazonaws.com', 'localhost', '3.39.220.146']

# CORS_ALLOWED_ORIGINS = [
#    "https://develop.d3t1tnno5uz3sa.amplifyapp.com",
#    "http://localhost:3000",
# ]

FRONTEND_URL = 'https://diivers.world'
