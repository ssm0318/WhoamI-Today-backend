from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from user_report.models import UserReport
from user_report.serializers import UserReportSerializer

from adoorback.utils.alerts import send_user_event_to_slack
from adoorback.utils.validators import adoor_exception_handler

User = get_user_model()


class UserReportList(generics.CreateAPIView):
    """
    List all user reports, or create a new user report
    """
    queryset = UserReport.objects.all()
    serializer_class = UserReportSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        reporter = self.request.user
        reported_user_id = self.request.data['reported_user_id']
        try:
            serializer.save(user=reporter, reported_user_id=reported_user_id)
        except IntegrityError:
            return

        reported_user = User.objects.filter(id=reported_user_id).only('username').first()
        reported_username = reported_user.username if reported_user else '(deleted)'
        send_user_event_to_slack(
            f"*🚩 User Report*\n"
            f"```\n"
            f"Reporter: {reporter.username} (ID: {reporter.id})\n"
            f"Target: {reported_username} (ID: {reported_user_id})\n"
            f"```"
        )
