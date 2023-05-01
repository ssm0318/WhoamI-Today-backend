from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework import status


class InActiveUser(AuthenticationFailed):
    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = _("이미 가입되었으나 인증이 완료되지 않은 계정입니다. 인증 메일을 확인해주세요.")
    default_code = 'user_is_inactive'


class NoUsername(AuthenticationFailed):
    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = _("존재하지 않는 닉네임/이메일입니다.")
    default_code = 'username_does_not_exist'


class WrongPassword(AuthenticationFailed):
    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = _("비밀번호를 다시 확인해주세요.")
    default_code = 'wrong_password'


class ExistingUsername(APIException):
    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = _("이미 존재하는 닉네임입니다.")
    default_code = 'username_exists'


class LongUsername(APIException):
    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = _("닉네임은 20글자 이하로 설정해주세요.")
    default_code = 'username_too_long'


class InvalidUsername(APIException):
    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = _("유효하지 않은 닉네임입니다. 닉네임은 영어, 한글, 숫자, 특수문자(_)만 포함할 수 있습니다.")
    default_code = 'username_invalid'


class ExistingEmail(APIException):
    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = _("이미 가입된 이메일입니다.")
    default_code = 'email_exists'


class InvalidEmail(APIException):
    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = _("유효하지 않은 이메일 형식입니다.")
    default_code = 'email_invalid'
