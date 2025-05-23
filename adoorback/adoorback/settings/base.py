"""
Django settings for adoorback project.

Generated by 'django-admin startproject' using Django 3.1.2.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""

import os
from pathlib import Path
import os.path
from datetime import timedelta

from firebase_admin import credentials
from firebase_admin import initialize_app
from django.utils.translation import gettext_lazy as _
import ssl


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ['SECRET_KEY']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField' # django 버전업하면서 추가

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'adoorback.utils.authentication.CustomAuthentication',
        'adoorback.utils.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=365),
    
    # custom
    'AUTH_COOKIE': 'access_token',  # Cookie name. Enables cookies if value is set.
    'AUTH_COOKIE_MAX_AGE': 60 * 60 * 24 * 365, # access token cookie max age. same as JWT ACCESS_TOKEN_LIFETIME.
    'AUTH_COOKIE_SECURE': False,
    'AUTH_COOKIE_HTTP_ONLY' : True,
    'AUTH_COOKIE_SAMESITE': 'Lax',  # Whether to set the flag restricting cookie leaks on cross-site requests. This can be 'Lax', 'Strict', or None to disable the flag.
}

CORS_ORIGIN_WHITELIST = [
    "https://develop.d3t1tnno5uz3sa.amplifyapp.com",
    "http://localhost:8000",
]

# Application definition

INSTALLED_APPS = [
    'adoorback.apps.AdoorbackConfig',
    'daphne',
    'account.apps.AccountConfig',
    'channels',
    'chat.apps.ChatConfig',
    'qna.apps.QnaConfig',
    'check_in.apps.CheckInConfig',
    'note.apps.NoteConfig',
    'like.apps.LikeConfig',
    'comment.apps.CommentConfig',
    'notification.apps.NotificationConfig',
    'user_tag.apps.UserTagConfig',
    'reaction.apps.ReactionConfig',
    'content_report.apps.ContentReportConfig',
    'user_report.apps.UserReportConfig',
    'translate.apps.TranslateConfig',
    'ping.apps.PingConfig',
    'custom_fcm',
    'modeltranslation',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'rest_framework',
    'polymorphic',
    'django_cron',
    'django_countries',
    'corsheaders',
    'import_export',
    'trackstats',
    'safedelete',
    'tracking',
]

SITE_ID = 1

AUTH_USER_MODEL = 'account.User'

LOGIN_REDIRECT_URL = '/api/user/'

CRON_CLASSES = [
    "qna.cron.DailyQuestionCronJob",
    "account.cron.SendDailyWhoAmINotiCronJob",
    "account.cron.AutoCloseSessionsCronJob",
    "account.cron.SendDailySurveyNotiCronJob",
]

# reference: https://github.com/jazzband/django-redis
# CACHES = {
#     "default": {
#         "BACKEND": "django_redis.cache.RedisCache",
#         "LOCATION": "redis://127.0.0.1:6379/1",
#         "OPTIONS": {
#             "CLIENT_CLASS": "django_redis.client.DefaultClient",
#         }
#     }
# }

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware', # CorsMiddleware should be placed as high as possible, especially before any middleware that can generate responses such as Django's CommonMiddleware
    'adoorback.middleware.CustomLocaleMiddleware',
    'tracking.middleware.VisitorTrackingMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'adoorback.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'adoorback.wsgi.application'
ASGI_APPLICATION = 'adoorback.asgi.application'

REDIS_URL = os.getenv('REDIS_URL')

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [{
                "address": REDIS_URL,
                "ssl_cert_reqs": None,  # This disables SSL certificate validation
            }],
        },
    },
}

# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    {'NAME': 'adoorback.utils.validators.NumberValidator', },
    {'NAME': 'adoorback.utils.validators.UppercaseValidator', },
    {'NAME': 'adoorback.utils.validators.LowercaseValidator', },
    {'NAME': 'adoorback.utils.validators.SymbolValidator', },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
]

# Password reset token timeout (1 hour in seconds)
PASSWORD_RESET_TIMEOUT = 60 * 60 

# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = 'en'

gettext = lambda s: s
LANGUAGES = (
    ('ko', gettext('한국어')),
    ('en', gettext('영어')),
)

TIME_ZONE = 'America/Los_Angeles'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'adoorback', 'media')

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_USE_TLS = True
EMAIL_PORT = 587
EMAIL_HOST = 'smtp.gmail.com' 
EMAIL_HOST_USER = 'whoami.today.official@gmail.com'
EMAIL_HOST_PASSWORD = os.environ['EMAIL_HOST_PASSWORD']
SERVER_EMAIL = 'whoami.today.official@gmail.com'

# https://fcm-django.readthedocs.io/en/latest/
FIREBASE_CREDENTIAL_PATH = os.path.join(BASE_DIR, 'serviceAccountKey.json')
FIREBASE_CREDENTIAL = credentials.Certificate(FIREBASE_CREDENTIAL_PATH)
FIREBASE_APP = initialize_app(FIREBASE_CREDENTIAL)
FCM_DJANGO_SETTINGS = {
    # an instance of firebase_admin.App to be used as default for all fcm-django requests
    # default: None (the default Firebase app)
    "DEFAULT_FIREBASE_APP": None,
    # default: _('FCM Django')
    "APP_VERBOSE_NAME": "[string for AppConfig's verbose_name]",
    # true if you want to have only one active device per registered user at a time
    # default: False
    "ONE_DEVICE_PER_USER": False,
    # devices to which notifications cannot be sent,
    # are deleted upon receiving error response from FCM
    # default: False
    "DELETE_INACTIVE_DEVICES": False,
    # Transform create of an existing Device (based on registration id) into
            # an update. See the section
    # "Update of device with duplicate registration ID" for more details.
    # default: False
    "UPDATE_ON_DUPLICATE_REG_ID": True,
    "FCM_DEVICE_MODEL": "custom_fcm.CustomFCMDevice", 
}

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

AUTHENTICATION_BACKENDS = ('account.backends.CustomModelBackend',)

SESSION_ENGINE = "django.contrib.sessions.backends.file"
SESSION_FILE_PATH = os.path.join(BASE_DIR, 'sessions')
TRACK_ANONYMOUS_USERS = False
TRACK_IGNORE_STATUS_CODES = [400, 404, 403, 405, 410, 500]


LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} [{username} ({user_id})] {message} (Token: {token}, Page: {page}, OS: {os}, Body: {body})',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
            'class': 'adoorback.safe_formatter.SafeFormatter',
        },
        'detailed': {
            'format': '\n' + '='*50 + '\n{asctime} [{levelname}] User: {username} ({user_id}) ({os})\nPage: {page}\nBody:\n\t{body}\nLogger: {name}\nPath: {pathname}:{lineno}\nMessage: {message}\nToken: {token}\n' + '='*50 + '\n',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
            'class': 'adoorback.safe_formatter.SafeFormatter',
        },
    },
    'filters': {
        'add_user_info': {
            '()': 'adoorback.filters.UserInfoFilter',
        },
    },
    'handlers': {
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'error.log'),
            'when': 'midnight',
            'interval': 1,
            'formatter': 'detailed',
            'filters': ['add_user_info'],
        },
        'info_file': {
            'level': 'INFO',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'info.log'),
            'when': 'midnight',
            'interval': 1,
            'formatter': 'verbose',
            'filters': ['add_user_info'],
        },
        'debug_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'debug.log'),
            'when': 'midnight',
            'interval': 1,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['error_file', 'info_file', 'debug_file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['error_file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['error_file', 'info_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'adoorback': {
            'handlers': ['error_file', 'info_file', 'debug_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
