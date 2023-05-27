# import sentry_sdk
import re
from difflib import SequenceMatcher

from django.contrib.auth.password_validation import UserAttributeSimilarityValidator, exceeds_maximum_length_ratio
from django.core import validators
from django.core.exceptions import ValidationError, FieldDoesNotExist
from django.utils.translation import gettext_lazy as _
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


class NumberValidator(object):
    def validate(self, password, user=None):
        if not re.findall('\d', password):
            raise ValidationError(
                _("비밀번호는 숫자(0-9)를 한 개 이상 포함해야 합니다."),
                code='password_no_number',
            )

    def get_help_text(self):
        return _(
            "비밀번호는 숫자(0-9)를 한 개 이상 포함해야 합니다."
        )


class UppercaseValidator(object):
    def validate(self, password, user=None):
        if not re.findall('[A-Z]', password):
            raise ValidationError(
                _("비밀번호는 알파벳 대문자(A-Z)를 한 개 이상 포함해야 합니다."),
                code='password_no_upper',
            )

    def get_help_text(self):
        return _(
            "비밀번호는 알파벳 대문자(A-Z)를 한 개 이상 포함해야 합니다."
        )


class LowercaseValidator(object):
    def validate(self, password, user=None):
        if not re.findall('[a-z]', password):
            raise ValidationError(
                _("비밀번호는 알파벳 소문자(a-z)를 한 개 이상 포함해야 합니다."),
                code='password_no_lower',
            )

    def get_help_text(self):
        return _(
            "비밀번호는 알파벳 소문자(a-z)를 한 개 이상 포함해야 합니다."
        )


class SymbolValidator(object):
    def validate(self, password, user=None):
        if not re.findall('[()[\]{}|\\`~!@#$%^&*_\-+=;:\'",<>./?]', password):
            raise ValidationError(
                _("비밀번호는 특수문자를 한 개 이상 포함해야 합니다: " +
                  "()[]{}|\`~!@#$%^&*_-+=;:'\",<>./?"),
                code='password_no_symbol',
            )

    def get_help_text(self):
        return _(
            "비밀번호는 특수문자를 한 개 이상 포함해야 합니다: " +
            "()[]{}|\`~!@#$%^&*_-+=;:'\",<>./?"
        )
    

class CustomUserAttributeSimilarityValidator(UserAttributeSimilarityValidator):
    def validate(self, password, user=None):
        if not user:
            return

        password = password.lower()
        for attribute_name in self.user_attributes:
            value = getattr(user, attribute_name, None)
            if not value or not isinstance(value, str):
                continue
            value_lower = value.lower()
            value_parts = re.split(r'\W+', value_lower) + [value_lower]
            for value_part in value_parts:
                if exceeds_maximum_length_ratio(password, self.max_similarity, value_part):
                    continue
                if SequenceMatcher(a=password, b=value_part).quick_ratio() >= self.max_similarity:
                    if attribute_name == 'email':
                        message = _("비밀번호가 이메일과 너무 유사합니다.")
                    elif attribute_name == 'username':
                        message = _("비밀번호가 닉네임과 너무 유사합니다.")
                    else:
                        try:
                            verbose_name = str(user._meta.get_field(attribute_name).verbose_name)
                        except FieldDoesNotExist:
                            verbose_name = attribute_name
                        message = _("비밀번호가 ") + verbose_name + _("와 너무 유사합니다.")
                    raise ValidationError(
                        message,
                        code='password_too_similar',
                        params={'verbose_name': attribute_name},
                    )
