from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from adoorback.utils.content_types import get_generic_relation_type
from comment.models import Comment
from content_report.models import ContentReport
from like.models import Like

User = get_user_model()


class AdoorBaseSerializer(serializers.ModelSerializer):
    comment_count = serializers.SerializerMethodField(read_only=True)
    like_count = serializers.SerializerMethodField(read_only=True)
    current_user_like_id = serializers.SerializerMethodField(read_only=True)

    def validate(self, attrs):
        if len(attrs.get('content')) == 0:
            raise serializers.ValidationError('내용은 최소 한 글자 이상 써야해요...')
        return attrs

    def get_comment_count(self, obj):
        request = self.context.get('request', None)
        if request is None or not request.user.is_authenticated:
            return 0

        if obj.type not in ["Note", "Response", "Comment"]:
            return None
    
        current_user = request.user
        blocked_user_ids = current_user.user_report_blocked_ids

        comment_ct = ContentType.objects.get_for_model(Comment)
        blocked_comment_ids = ContentReport.objects.filter(
            user=current_user,
            content_type=comment_ct
        ).values_list('object_id', flat=True)

        def filter_comments(queryset):
            return queryset.exclude(
                Q(id__in=blocked_comment_ids) | Q(author_id__in=blocked_user_ids)
            )

        if obj.type == "Note":
            comments = filter_comments(obj.note_comments.all())
            replies_count = sum(filter_comments(comment.replies.all()).count() for comment in comments)
            return comments.count() + replies_count

        elif obj.type == "Response":
            comments = filter_comments(obj.response_comments.all())
            replies_count = sum(filter_comments(comment.replies.all()).count() for comment in comments)
            return comments.count() + replies_count

        elif obj.type == "Comment":
            return filter_comments(obj.replies.all()).count()

        return None

    def get_like_count(self, obj):
        current_user = self.context['request'].user

        if obj.author != current_user:
            return None

        blocked_user_ids = current_user.user_report_blocked_ids
        return obj.liked_user_ids.exclude(id__in=blocked_user_ids).count()

    def get_current_user_like_id(self, obj):
        current_user_id = self.context['request'].user.id
        content_type_id = get_generic_relation_type(obj.type).id
        like = Like.objects.filter(user_id=current_user_id, content_type_id=content_type_id, object_id=obj.id)
        return like[0].id if like else None

    class Meta:
        model = None
        fields = ['id', 'type', 'content', 'comment_count' ,'like_count', 'current_user_like_id', 'created_at',
                  'updated_at']
        validators = []
