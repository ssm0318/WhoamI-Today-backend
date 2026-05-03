import re
import traceback

from django.core import validators
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import NotAuthenticated, AuthenticationFailed, PermissionDenied, Throttled
from rest_framework.views import exception_handler

from adoorback.utils.alerts import send_msg_to_slack, send_gmail_alert
from adoorback.utils.exceptions import (
    WrongPassword, NoUsername, InActiveUser,
    ExistingUsername, LongUsername, InvalidUsername,
    ExistingEmail, InvalidEmail, ExistingReaction,
    NoSuchTarget, NotFriend, ExistingResponseRequest,
    NoSuchQuestion, DeletedQuestion, ConflictError,
)


USERNAME_REGEX = r'^[가-힣\w@.\-]+\Z'
USER_INPUT_EXCEPTIONS = (
    ExistingUsername, LongUsername, InvalidUsername,
    ExistingEmail, InvalidEmail, ExistingReaction,
    NoSuchTarget, NotFriend, ExistingResponseRequest,
    NoSuchQuestion, DeletedQuestion, ConflictError,
)


class NonReportingValidationError(ValidationError):
    slack_level = None


def validate_notification_message(message):
    if message not in ['sent friend request to',
                       'received friend request from',
                       'refused friend request of',
                       'accepted friend request of']:
        raise ValidationError(
            '%(message)s is not a valid message',
            params={'message': message},
        )


def adoor_exception_handler(exc, context):
    view = context.get('view', None)
    request = context.get('request', None)
    tb = traceback.format_exc()

    # Ignore PermissionDenied unless it's a CSRF failure message
    if isinstance(exc, PermissionDenied):
        if not str(exc).startswith("CSRF Failed"):
            return exception_handler(exc, context)

    # Slack notification
    # Ignore authentication failures, throttling, and user input related exceptions
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed, Throttled)) or isinstance(exc, USER_INPUT_EXCEPTIONS):
        return exception_handler(exc, context)

    slack_level = getattr(exc, 'slack_level', 'ERROR')  # Default is ERROR

    # Ignore ValidationError based on message
    if isinstance(exc, ValidationError):
        flat_messages = list(flatten_validation_errors(exc.detail))
        skip_messages = {
            "This field may not be blank.",
            "이 필드는 필수 항목입니다.",
            "This field is required.",
            "Cannot send friend requests to users using different versions",
            "Friend request already sent.",
        }
        if all(msg in skip_messages for msg in flat_messages):
            slack_level = None

    if slack_level:
        try:
            send_msg_to_slack(
                text=f"*🚨 예외 발생 in {view.__class__.__name__ if view else 'Unknown'}*\n```{tb}```",
                level="ERROR"
            )
        except Exception:
            traceback.print_exc()

    # # Email notification
    # try:
    #     send_gmail_alert(
    #         subject="🚨 Django Exception Occurred",
    #         body=f"""
    #         View: {view.__class__.__name__ if view else 'Unknown'}
    #         Method: {request.method if request else 'N/A'}
    #         URL: {request.build_absolute_uri() if request else 'N/A'}

    #         Exception:
    #         {str(exc)}

    #         Traceback:
    #         {tb}
    #         """,
    #     )
    # except Exception:
    #     traceback.print_exc()

    return exception_handler(exc, context)


# Helper to flatten nested dict/list validation errors
def flatten_validation_errors(detail):
    if isinstance(detail, list):
        for item in detail:
            yield from flatten_validation_errors(item)
    elif isinstance(detail, dict):
        for item in detail.values():
            yield from flatten_validation_errors(item)
    else:
        yield str(detail)


class AdoorUsernameValidator(validators.RegexValidator):
    regex = USERNAME_REGEX
    message = _(
        '유효한 닉네임을 입력해주세요. 영문, 한글, 숫자, 일부 특수문자(_)만 허용합니다.'
        '공백, 한글 자음/모음만 있는 경우는 허용되지 않습니다.'
    )
    flags = 0

    def __call__(self, value):
        if not self.regex.match(value):
            raise NonReportingValidationError(self.message)


class NumberValidator(object):
    def validate(self, password, user=None):
        if not re.findall('\d', password):
            raise NonReportingValidationError(
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
            raise NonReportingValidationError(
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
            raise NonReportingValidationError(
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
            raise NonReportingValidationError(
                _("비밀번호는 특수문자를 한 개 이상 포함해야 합니다: " +
                  "()[]{}|\`~!@#$%^&*_-+=;:'\",<>./?"),
                code='password_no_symbol',
            )

    def get_help_text(self):
        return _(
            "비밀번호는 특수문자를 한 개 이상 포함해야 합니다: " +
            "()[]{}|\`~!@#$%^&*_-+=;:'\",<>./?"
        )
    