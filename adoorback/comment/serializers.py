from itertools import chain

from django.contrib.auth import get_user_model
from django.db.models import F, Value, CharField, BooleanField
from rest_framework import serializers
from django.urls import reverse

from comment.models import Comment

from adoorback.serializers import AdoorBaseSerializer
from adoorback.utils.content_types import get_generic_relation_type
from django.conf import settings
from account.serializers import UserMinimalSerializer
from note.models import Note
from qna.models import Response
from reaction.models import Reaction
from user_tag.serializers import UserTagSerializer

User = get_user_model()


class RecursiveReplyField(serializers.Serializer):
    def to_representation(self, value):
        serializer = self.parent.parent.__class__(value, context=self.context)
        return serializer.data


class CommentBaseSerializer(AdoorBaseSerializer):
    is_reply = serializers.SerializerMethodField(read_only=True)
    target_id = serializers.SerializerMethodField()
    user_tags = serializers.SerializerMethodField()
    like_user_sample = serializers.SerializerMethodField(read_only=True)
    like_reaction_user_sample = serializers.SerializerMethodField(read_only=True)
    current_user_reaction_id_list = serializers.SerializerMethodField(read_only=True)

    def get_is_reply(self, obj):
        return obj.target.type == 'Comment'

    def get_target_id(self, obj):
        return obj.object_id

    def get_user_tags(self, obj):
        user_tags = obj.comment_user_tags
        return UserTagSerializer(user_tags, many=True, read_only=True, context=self.context).data
    
    def get_like_user_sample(self, obj):
        from account.serializers import UserMinimalSerializer
        recent_likes = obj.comment_likes.order_by('-created_at')[:3]
        recent_users = [like.user for like in recent_likes]
        return UserMinimalSerializer(recent_users, many=True, context=self.context).data

    def get_like_reaction_user_sample(self, obj):
        blocked_ids = self.context['request'].user.user_report_blocked_ids
        likes = obj.comment_likes.exclude(user_id__in=blocked_ids).annotate(
            created=F('created_at'),
            like=Value(True, output_field=BooleanField()),
            reaction=Value(None, output_field=CharField())
        ).values('user', 'created', 'like', 'reaction')

        reactions = obj.reactions.exclude(user_id__in=blocked_ids).annotate(
            created=F('created_at'),
            like=Value(False, output_field=BooleanField()),
            reaction=F('emoji')
        ).values('user', 'created', 'like', 'reaction')

        combined = sorted(
            chain(likes, reactions),
            key=lambda x: x['created'],
            reverse=True
        )[:3]

        return [
            {**UserMinimalSerializer(User.objects.get(id=item['user']), context=self.context).data,
             'like': item['like'], 'reaction': item['reaction']}
            for item in combined
        ]

    def get_current_user_reaction_id_list(self, obj):
        current_user_id = self.context['request'].user.id
        content_type_id = get_generic_relation_type(obj.type).id
        reactions = Reaction.objects.filter(user_id=current_user_id, content_type_id=content_type_id, object_id=obj.id)
        return [{"id": reaction.id, "emoji": reaction.emoji} for reaction in reactions]

    class Meta(AdoorBaseSerializer.Meta):
        model = Comment
        fields = AdoorBaseSerializer.Meta.fields + ['is_reply', 'is_private', 'target_id', 'user_tags', 'like_user_sample', 'like_reaction_user_sample', 'current_user_reaction_id_list']


class CommentFriendSerializer(CommentBaseSerializer):
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    replies = serializers.SerializerMethodField()

    def get_author(self, obj):
        return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})

    def get_replies(self, obj):
        current_user = self.context.get('request', None).user
        replies = obj.replies.exclude(author_id__in=current_user.user_report_blocked_ids).order_by('created_at')

        def serialize_reply(reply):
            if (reply.author != current_user
                and reply.target.author != current_user
                and reply.target.target.author != current_user
                and reply.is_private):
                return {'id': reply.id, 'is_private': True}
            else:
                return self.__class__(reply, read_only=True, context=self.context).data

        return [serialize_reply(reply) for reply in replies]

    def to_representation(self, instance):
        current_user = self.context.get('request', None).user
        if (instance.author != current_user
            and instance.target.author != current_user
            and getattr(instance.target, 'target', None) is None
            and instance.is_private):
            return {'id': instance.id, 'is_private': True}
        else:
            return super().to_representation(instance)


    class Meta(CommentBaseSerializer.Meta):
        model = Comment
        fields = CommentBaseSerializer.Meta.fields + ['author', 'author_detail', 'replies']


class ReplySerializer(CommentFriendSerializer):

    class Meta(CommentFriendSerializer.Meta):
        model = Comment
