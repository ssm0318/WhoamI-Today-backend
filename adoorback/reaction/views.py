from django.db import transaction, IntegrityError
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from reaction.models import Reaction
from reaction.serializers import ReactionSerializer

from adoorback.utils.permissions import IsOwnerOrReadOnly
from adoorback.utils.content_types import get_generic_relation_type
from adoorback.utils.validators import adoor_exception_handler
from adoorback.utils.exceptions import ExistingReaction, NoSuchTarget, NotFriend


class ReactionList(generics.ListCreateAPIView):
    """
    List all reactions, or create a new reaction.
    """
    queryset = Reaction.objects.all()
    serializer_class = ReactionSerializer
    permission_classes = [IsAuthenticated]

    def validate_target(self):
        try:
            content_type = get_generic_relation_type(self.kwargs.get('ctype'))
            object_id = self.kwargs.get('oid')
            target = content_type.model_class().objects.get(id=object_id)

            return [target, content_type.id, object_id]
        except Exception:
            raise NoSuchTarget()

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        target, content_type_id, object_id = self.validate_target()
        if target.author != self.request.user:
            return Reaction.objects.filter(object_id=object_id, content_type_id=content_type_id, user=self.request.user).order_by('-created_at')
        return Reaction.objects.filter(object_id=object_id, content_type_id=content_type_id).order_by('-created_at')

    @transaction.atomic
    def perform_create(self, serializer):
        target, content_type_id, object_id = self.validate_target()

        if target.author != self.request.user and not target.author.is_connected(self.request.user):
            raise NotFriend()

        try:
            serializer.save(user=self.request.user,
                            content_type_id=content_type_id,
                            object_id=object_id)
        except IntegrityError as e:
            if 'unique_reaction' in e.args[0]:
                raise ExistingReaction()


class ReactionDestroy(generics.DestroyAPIView):
    """
    Destroy a reaction.
    """
    queryset = Reaction.objects.all()
    serializer_class = ReactionSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler
