from django.contrib.contenttypes.models import ContentType
from django.db import transaction, IntegrityError
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from content_report.models import ContentReport
from content_report.serializers import ContentReportSerializer

from adoorback.utils.content_types import get_generic_relation_type
from adoorback.utils.validators import adoor_exception_handler


class ContentReportList(generics.ListCreateAPIView):
    queryset = ContentReport.objects.all()
    serializer_class = ContentReportSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        content_type = self.request.data.get('target_type')
        content_type_id = get_generic_relation_type(content_type).id
        object_id = self.request.data.get('target_id')

        if content_type and object_id:
            serializer.save(user=user, content_type_id=content_type_id, object_id=object_id)
