from django.contrib.contenttypes.models import ContentType
from rest_framework import permissions

from adoorback.utils.content_types import get_generic_relation_type


class IsAuthorOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow authors of an article/comment to edit/delete it.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author == request.user


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of objects to update/destroy.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user


class IsShared(permissions.BasePermission):
    """
    Custom permission to only allow friends of author to view.
    """

    def has_object_permission(self, request, view, obj):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        if obj.type == 'Question':
            return True
        elif User.are_friends(request.user, obj.author):
            return True
        else:
            return obj.author == request.user


class IsNotBlocked(permissions.BasePermission):
    """
    Custom permission to only display contents (of users) that are not blocked.
    """

    def has_object_permission(self, request, view, obj):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        from note.models import Note
        from qna.models import Response
        from check_in.models import CheckIn

        if obj.type in ['Response', 'Note', 'CheckIn']:
            is_model = True
        else:
            is_model = False

        if is_model:
            current_content_type = ContentType.objects.get_for_model(obj).model

            blocked_contents = request.user.content_report_blocked_model_ids

            content_blocked = (current_content_type, obj.id) in blocked_contents

            author_blocked = obj.author.id in request.user.user_report_blocked_ids

            return not (content_blocked or author_blocked)

        return True
