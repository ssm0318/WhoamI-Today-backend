import datetime
import six
import traceback

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import EmailMessage
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.encoding import force_bytes
from django.utils.http import base36_to_int, urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _

from adoorback.utils.alerts import send_msg_to_slack


class ActivateTokenGenerator(PasswordResetTokenGenerator):
    EMAIL_VERIFICATION_TIMEOUT_SECONDS = 60 * 60 * 24 * 365  # 1년

    def _make_hash_value(self, user, timestamp):
        return (six.text_type(user.pk) + six.text_type(timestamp)) + six.text_type(user.email_verified)
    
    def check_token(self, user, token):
        """
        Check that a password reset token is correct for a given user.
        """
        if not (user and token):
            return False
        # Parse the token
        try:
            ts_b36, _ = token.split("-")
        except ValueError:
            return False

        try:
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False

        # Check that the timestamp/uid has not been tampered with
        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(
                self._make_token_with_timestamp(user, ts, secret),
                token,
            ):
                break
        else:
            return False

        # Check the timestamp is within limit.
        if (self._num_seconds(self._now()) - ts) > self.EMAIL_VERIFICATION_TIMEOUT_SECONDS:
            return False

        return True


class EmailManager():
    activate_token_generator = ActivateTokenGenerator()
    pw_reset_token_generator = PasswordResetTokenGenerator()

    def send_verification_email(self, user):
        token = self.activate_token_generator.make_token(user)

        uid = urlsafe_base64_encode(force_bytes(user.pk))

        mail_title = _("[WIT] 이메일 인증을 완료해주세요")
        mail_to = [user.email]
        message_data = _("이메일 인증을 위해 아래 링크를 클릭해주세요.\n\n이메일 인증 링크: ")
        message_data += f"{settings.FRONTEND_URL}/activate/{uid}/{token}/\n\n"
        message_data += _("감사합니다.")
        email = EmailMessage(mail_title, message_data, to=mail_to)
        try:
            email.send(fail_silently=False)
        except Exception as e:
            tb = traceback.format_exc()
            send_msg_to_slack(
                text=f"*⚠️ 이메일 인증 이메일 전송 실패*\n```{tb}```",
                level="WARNING"
            )


    def send_reset_password_email(self, user):
        token = self.pw_reset_token_generator.make_token(user)
        
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        mail_title = _("비밀번호 변경 링크입니다.")
        mail_to = [user.email]
        message_data = f"{user.username}"
        message_data += _("님, 아래 링크를 클릭하면 비밀번호 변경이 가능합니다.\n\n비밀번호 변경 링크: ")
        message_data += f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}\n\n"
        message_data += _("감사합니다.")
        email = EmailMessage(mail_title, message_data, to=mail_to)
        email.send()

    def check_activate_token(self, user, token):
        return self.activate_token_generator.check_token(user, token)

    def check_reset_password_token(self, user, token):
        return self.pw_reset_token_generator.check_token(user, token)

email_manager = EmailManager()
