from django.db import transaction, IntegrityError
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from user_report.models import UserReport
from user_report.serializers import UserReportSerializer

from adoorback.utils.permissions import IsNotBlocked
from adoorback.utils.content_types import get_generic_relation_type
from adoorback.utils.validators import adoor_exception_handler


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
        try:
            serializer.save(user=self.request.user,
                            reported_user_id=self.request.data['reported_user_id'])
        except IntegrityError:
            pass
