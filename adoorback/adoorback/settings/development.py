# import sentry_sdk
# from sentry_sdk.integrations.django import DjangoIntegration
from .base import *
import os

DEBUG = True

BASE_URL = 'http://localhost:8000'  

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'diivers',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'PORT': '5432',
    },
}

# sentry_sdk.init(
#     dsn="https://3525cb8e094e49fe9973fd92ccbf456b@o486285.ingest.sentry.io/5543025",
#     integrations=[DjangoIntegration()],
#     traces_sample_rate=1.0,

#     send_default_pii=True
# )

ALLOWED_HOSTS = ['*']

CORS_ALLOWED_ORIGINS = ['http://localhost:3000']
CSRF_TRUSTED_ORIGINS = ['http://localhost:3000']
CORS_ALLOW_CREDENTIALS = True
CSRF_COOKIE_HTTPONLY = False 
CSRF_COOKIE_SAMESITE = 'Lax'

FRONTEND_URL = 'http://localhost:3000'
