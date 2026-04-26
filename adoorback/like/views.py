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
        content_type = get_generic_relation_type(self.request.data['target_type'])
        content_type_id = content_type.id

        # Version isolation: block liking content from users on a different version
        target_model = content_type.model_class()
        try:
            target_obj = target_model.objects.get(id=self.request.data['target_id'])
            target_author = getattr(target_obj, 'author', None) or getattr(target_obj, 'user', None)
            if target_author and target_author.current_ver != self.request.user.current_ver:
                raise ValidationError("Cannot interact with content from a user on a different version.")
        except target_model.DoesNotExist:
            pass

        try:
            instance = serializer.save(
                user=self.request.user,
                content_type_id=content_type_id,
                object_id=self.request.data['target_id']
            )
            # Prevent error when accessing serializer.data: create new serializer based on instance
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
