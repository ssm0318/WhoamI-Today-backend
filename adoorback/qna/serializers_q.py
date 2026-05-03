from django.contrib.auth import get_user_model
from django.db.models import F, Value, CharField, BooleanField
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from account.serializers import UserMinimalSerializer
from adoorback.serializers import AdoorBaseSerializer
from qna.models import Response
from qna.serializers import QuestionMinimumSerializer

User = get_user_model()


class QResponseSerializer(AdoorBaseSerializer):
    """
    Response serializer for Version Q.
    - Likes only (no reactions)
    """
    author = serializers.HyperlinkedRelatedField(
        view_name='user-detail', read_only=True, lookup_field='username', lookup_url_kwarg='username')
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    question = QuestionMinimumSerializer(read_only=True)
    question_id = serializers.IntegerField(write_only=True)
    current_user_read = serializers.SerializerMethodField(read_only=True)
    like_count = serializers.SerializerMethodField(read_only=True)
    like_user_sample = serializers.SerializerMethodField(read_only=True)
    visibility = serializers.MultipleChoiceField(
        choices=['public', 'friends', 'close_friends'],
        required=True
    )

    def validate_visibility(self, value):
        if len(value) != 1:
            raise serializers.ValidationError(_("Please select exactly one visibility option."))
        return list(value)

    def get_current_user_read(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.reader_ids

    def get_like_count(self, obj):
        request = self.context.get('request')
        qs = obj.response_likes.all()
        if request is not None and request.user.is_authenticated:
            qs = qs.exclude(user_id__in=request.user.user_report_blocked_ids)
        return qs.count()

    def get_like_user_sample(self, obj):
        request = self.context.get('request')
        qs = obj.response_likes.order_by('-created_at')
        if request is not None and request.user.is_authenticated:
            qs = qs.exclude(user_id__in=request.user.user_report_blocked_ids)
        recent_users = [like.user for like in qs[:3]]
        return UserMinimalSerializer(recent_users, many=True, context=self.context).data

    class Meta(AdoorBaseSerializer.Meta):
        model = Response
        fields = AdoorBaseSerializer.Meta.fields + [
            'id', 'type', 'author', 'author_detail', 'content',
            'current_user_like_id', 'question', 'question_id',
            'created_at', 'current_user_read',
            'like_count', 'like_user_sample',
            'is_edited', 'visibility'
        ]
