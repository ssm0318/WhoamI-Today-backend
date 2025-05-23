from django.db import transaction, IntegrityError
from django.utils.translation import gettext_lazy as _
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from adoorback.utils.content_types import get_generic_relation_type
from adoorback.utils.permissions import IsOwnerOrReadOnly
from adoorback.utils.validators import adoor_exception_handler
from like.models import Like
from like.serializers import LikeSerializer


class LikeCreate(generics.CreateAPIView):
    queryset = Like.objects.all()
    serializer_class = LikeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        content_type_id = get_generic_relation_type(self.request.data['target_type']).id
        try:
            instance = serializer.save(
                user=self.request.user,
                content_type_id=content_type_id,
                object_id=self.request.data['target_id']
            )
            # serializer.data 접근 시 에러 방지: instance 기준으로 새 serializer 만들어줌
            self.instance = instance  # for use in get_success_headers
        except IntegrityError:
            raise ValidationError({
                "detail": _("이미 좋아요를 눌렀어요."),
                "code": "duplicate_like"
            })
    
    # @transaction.atomic
    # def perform_create(self, serializer):
    #     content_type_id = get_generic_relation_type(self.request.data['target_type']).id
    #     try:
    #         serializer.save(user=self.request.user,
    #                         content_type_id=content_type_id,
    #                         object_id=self.request.data['target_id'])
    #     except IntegrityError:
    #         raise ValidationError("You have already liked this.")


class LikeDestroy(generics.DestroyAPIView):
    queryset = Like.objects.all()
    serializer_class = LikeSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler
