# import sentry_sdk

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core import validators

# from rest_framework import status
from rest_framework.views import exception_handler


USERNAME_REGEX = r'^[가-힣|\w|_]+\Z'


def validate_notification_message(message):
    if message not in ['sent friend request to',
                       'received friend request from',
                       'refused friend request of',
                       'accepted friend request of']:
        raise ValidationError(
            '%(message)s is not a valid message',
            params={'message': message},
        )


def adoor_exception_handler(e, context):
    response = exception_handler(e, context)
    # if response.status_code in [status.HTTP_400_BAD_REQUEST,
    #                             status.HTTP_401_UNAUTHORIZED,
    #                             status.HTTP_405_METHOD_NOT_ALLOWED,
    #                             status.HTTP_404_NOT_FOUND,
    #                             status.HTTP_403_FORBIDDEN]:
    # sentry_sdk.capture_exception(e)
    return response


class AdoorUsernameValidator(validators.RegexValidator):
    regex = USERNAME_REGEX
    message = _(
        '유효한 닉네임을 입력해주세요. 영문, 한글, 숫자, 일부 특수문자(_)만 허용합니다.'
        '공백, 한글 자음/모음만 있는 경우는 허용되지 않습니다.'
    )
    flags = 0
