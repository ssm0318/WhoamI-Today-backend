from rest_framework import serializers
from django.contrib.auth import get_user_model

from notification.models import Notification
from feed.models import Question
from account.serializers import AuthorFriendSerializer, AuthorAnonymousSerializer

User = get_user_model()


class NotificationSerializer(serializers.ModelSerializer):
    is_response_request = serializers.SerializerMethodField(read_only=True)
    is_friend_request = serializers.SerializerMethodField(read_only=True)
    actor_detail = serializers.SerializerMethodField(read_only=True)
    question_content = serializers.SerializerMethodField(read_only=True)
    is_read = serializers.BooleanField(required=True)

    def get_is_response_request(self, obj):
        if obj.target is None:
            return False
        return obj.target.type == 'ResponseRequest'

    def get_is_friend_request(self, obj):
        if obj.target is None:
            return False
        return obj.target.type == 'FriendRequest'

    def get_actor_detail(self, obj):
        if obj.message_ko.startswith('익명의 사용자가 회원님의'):
            return AuthorAnonymousSerializer(obj.actor).data
        return AuthorFriendSerializer(obj.actor).data

    def get_question_content(self, obj):
        content = None
        if obj.target and (obj.target.type == 'ResponseRequest' or obj.target.type == 'Response'):
            content = obj.target.question.content
        # if question/response was deleted
        elif obj.target and obj.redirect_url[:11] == '/questions/' and obj.target.type != 'Like':
            content = Question.objects.get(id=int(obj.redirect_url[11:]))
        else:
            return content
        return content if len(content) <= 30 else content[:30] + '...'

    def validate(self, data):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError("이 필드는 뭘까요...: {}".format(", ".join(unknown)))
        if not data.get('is_read'):
            raise serializers.ValidationError("이미 읽은 노티를 안 읽음 표시할 수 없습니다...")
        return data

    class Meta:
        model = Notification
        fields = ['id', 'is_response_request', 'is_friend_request', 'actor_detail',
                  'message', 'question_content', 'is_read', 'created_at', 'redirect_url']
