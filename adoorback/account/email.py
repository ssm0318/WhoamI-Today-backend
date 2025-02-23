import six
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import EmailMessage
from django.utils.translation import gettext_lazy as _
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils.timezone import now
from datetime import timedelta


class EmailManager():
    pw_reset_token_generator = PasswordResetTokenGenerator()

    def send_reset_password_email(self, user):
        token = self.pw_reset_token_generator.make_token(user)
        
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        mail_title = _("비밀번호 변경 링크입니다.")
        mail_to = [user.email]
        message_data = f"{user.username}"
        message_data += _("님, 아래 링크를 클릭하면 비밀번호 변경이 가능합니다.\n\n비밀번호 변경 링크 : ")
        message_data += f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}\n\n"
        message_data += _("감사합니다.")
        email = EmailMessage(mail_title, message_data, to=mail_to)
        email.send()

    def check_reset_password_token(self, user, token):
        return self.pw_reset_token_generator.check_token(user, token)

email_manager = EmailManager()
