from django.contrib.auth import get_user_model
from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from note.models import Note
from note.serializers import BaseNoteSerializer, VisibilityField

User = get_user_model()


class QNoteSerializer(BaseNoteSerializer):
    """
    Note serializer for Version Q.
    - Likes only (no reactions)
    - No share_type field
    """
    like_count = serializers.SerializerMethodField(read_only=True)
    like_user_sample = serializers.SerializerMethodField(read_only=True)
    visibility = VisibilityField(choices=['only_me', 'close_friends', 'friends', 'public'], required=True)

    def validate_visibility(self, value):
        if len(value) != 1:
            raise serializers.ValidationError("Please select exactly one visibility option.")
        return list(value)

    def get_like_count(self, obj):
        request = self.context.get('request')
        qs = obj.note_likes.all()
        if request is not None and request.user.is_authenticated:
            qs = qs.exclude(user_id__in=request.user.user_report_blocked_ids)
        return qs.count()

    def get_like_user_sample(self, obj):
        request = self.context.get('request')
        qs = obj.note_likes.order_by('-created_at')
        if request is not None and request.user.is_authenticated:
            qs = qs.exclude(user_id__in=request.user.user_report_blocked_ids)
        recent_users = [like.user for like in qs[:3]]
        return UserMinimalSerializer(recent_users, many=True, context=self.context).data

    class Meta(BaseNoteSerializer.Meta):
        fields = BaseNoteSerializer.Meta.fields + ['like_count', 'like_user_sample', 'visibility']
