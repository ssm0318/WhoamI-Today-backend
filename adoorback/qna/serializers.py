from datetime import timedelta
from itertools import chain

from django.contrib.auth import get_user_model
from django.db.models import F, Value, CharField, BooleanField
from django.core.paginator import Paginator
from django.utils import timezone
from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from adoorback.serializers import AdoorBaseSerializer
from adoorback.utils.content_types import get_generic_relation_type
from qna.models import Response, Question, ResponseRequest
from reaction.models import Reaction

User = get_user_model()


class QuestionMinimumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'type', 'content']


class QuestionBaseSerializer(serializers.ModelSerializer):
    is_admin_question = serializers.SerializerMethodField(read_only=True)

    def get_is_admin_question(self, obj):
        return obj.author.is_superuser

    class Meta:
        model = Question
        fields = ['id', 'type', 'content', 'created_at', 'selected_dates', 
                  'selected', 'is_admin_question']


class QuestionGroupSerializer(serializers.Serializer):
    date = serializers.DateField()
    questions = serializers.ListField()


class ResponseSerializer(AdoorBaseSerializer):
    author = serializers.HyperlinkedRelatedField(
        view_name='user-detail', read_only=True, lookup_field='username', lookup_url_kwarg='username')
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    question = QuestionMinimumSerializer(read_only=True)
    question_id = serializers.IntegerField(write_only=True)
    current_user_read = serializers.SerializerMethodField(read_only=True)
    current_user_reaction_id_list = serializers.SerializerMethodField(read_only=True)
    like_reaction_user_sample = serializers.SerializerMethodField(read_only=True)
    visibility = serializers.ChoiceField(
        choices=['friends', 'close_friends'],
        required=True
    )

    def get_current_user_read(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.reader_ids

    def get_like_reaction_user_sample(self, obj):
        from account.serializers import UserMinimalSerializer
        
        likes = obj.response_likes.annotate(
            created=F('created_at'),
            like=Value(True, output_field=BooleanField()),
            reaction=Value(None, output_field=CharField())
        ).values('user', 'created', 'like', 'reaction')

        reactions = obj.reactions.annotate(
            created=F('created_at'),
            like=Value(False, output_field=BooleanField()),
            reaction=F('emoji')
        ).values('user', 'created', 'like', 'reaction')

        combined = sorted(
            chain(likes, reactions),
            key=lambda x: x['created'],
            reverse=True
        )[:3]

        serialized_data = []
        for reaction in combined:
            user = User.objects.get(id=reaction['user'])
            user_data = UserMinimalSerializer(user, context=self.context).data
            user_data['like'] = reaction['like']
            user_data['reaction'] = reaction['reaction']
            serialized_data.append(user_data)

        return serialized_data

    def get_current_user_reaction_id_list(self, obj):
        current_user_id = self.context['request'].user.id
        content_type_id = get_generic_relation_type(obj.type).id
        reactions = Reaction.objects.filter(user_id=current_user_id, content_type_id=content_type_id, object_id=obj.id)
        return [{"id": reaction.id, "emoji": reaction.emoji} for reaction in reactions]

    class Meta(AdoorBaseSerializer.Meta):
        model = Response
        fields = AdoorBaseSerializer.Meta.fields + ['id', 'type', 'author', 'author_detail', 'content', 'current_user_like_id',
                  'question', 'question_id', 'created_at', 'current_user_read', 'like_reaction_user_sample', 'current_user_reaction_id_list', 'is_edited', 'visibility']
        

class DailyQuestionSerializer(QuestionBaseSerializer):
    """
    (all profiles are anonymized, including that of the current user)
    """
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = serializers.SerializerMethodField(
        source='author', read_only=True)

    def get_author_detail(self, obj):
        return UserMinimalSerializer(obj.author).data

    def get_author(self, obj):
        return None

    class Meta(QuestionBaseSerializer.Meta):
        model = Question
        fields = QuestionBaseSerializer.Meta.fields + ['author', 'author_detail']


class ResponseRequestSerializer(serializers.ModelSerializer):
    requester_id = serializers.IntegerField()
    requestee_id = serializers.IntegerField()
    question_id = serializers.IntegerField()
    is_recent = serializers.SerializerMethodField(read_only=True)  # received in the last 7 days

    def validate(self, data):
        if data.get('requester_id') == data.get('requestee_id'):
            raise serializers.ValidationError('본인과는 친구가 될 수 없어요...')
        return data
    
    def get_is_recent(self, obj):
        if not hasattr(obj, 'created_at') or not obj.created_at:
            return False
        seven_days_ago = timezone.now() - timedelta(days=7)
        return obj.created_at >= seven_days_ago

    class Meta():
        model = ResponseRequest
        fields = ['id', 'requester_id', 'requestee_id', 'question_id', 'message', 'created_at', 'is_recent']


class GroupedResponseRequestSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    question_content = serializers.CharField()
    requester_username_list = serializers.ListField(child=serializers.CharField())
