from django.db import transaction
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from comment.models import Comment
from comment.serializers import CommentResponsiveSerializer

from adoorback.utils.permissions import IsAuthorOrReadOnly
from adoorback.utils.content_types import get_generic_relation_type
from adoorback.utils.validators import adoor_exception_handler
from utils.helpers import parse_user_tag_from_content
from utils.exceptions import BlockedUserTag, BlockingUserTag

class CommentCreate(generics.ListCreateAPIView):
    """
    List all comments
    """
    queryset = Comment.objects.order_by('id')
    serializer_class = CommentResponsiveSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        content_type_id = get_generic_relation_type(self.request.data['target_type']).id

        # check if blocked/blocking user is tagged
        tagged_users, _ = parse_user_tag_from_content(self.request.data['content'])
        tagging_user = self.request.user
        for tagged_user in tagged_users:
            if tagged_user.id in tagging_user.user_report_blocked_ids:
                raise BlockedUserTag()
            elif tagging_user.id in tagged_user.user_report_blocked_ids:
                raise BlockingUserTag()

        serializer.save(author=self.request.user,
                        content_type_id=content_type_id,
                        object_id=self.request.data['target_id'])


class CommentDetail(generics.DestroyAPIView):
    """
    Retrieve, update, or destroy a comment.
    """
    queryset = Comment.objects.all()
    serializer_class = CommentResponsiveSerializer
    permission_classes = [IsAuthenticated, IsAuthorOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler
