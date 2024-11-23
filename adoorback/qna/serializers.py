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
from category.serializers import CategorySerializer
from account.models import Category

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


class ResponseSerializer(AdoorBaseSerializer):
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    question = QuestionMinimumSerializer(read_only=True)
    question_id = serializers.IntegerField(write_only=True)
    current_user_read = serializers.SerializerMethodField(read_only=True)
    current_user_reaction_id_list = serializers.SerializerMethodField(read_only=True)
    like_reaction_user_sample = serializers.SerializerMethodField(read_only=True)
    category = CategorySerializer(read_only=True)
    category_id = serializers.IntegerField(write_only=True)
    sharing_scope = serializers.CharField(read_only=True)
    archived_at = serializers.DateTimeField(read_only=True)

    
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
                  'question', 'question_id', 'created_at', 'current_user_read', 'like_reaction_user_sample', 'current_user_reaction_id_list', 'is_edited',
                  'category', 'category_id', 'sharing_scope', 'archived_at']
        
    def create(self, validated_data):
        category = Category.objects.get(id=validated_data.pop('category_id'))
        validated_data['category'] = category
        validated_data['sharing_scope'] = category.sharing_scope
        return super().create(validated_data)


class QuestionResponseSerializer(QuestionBaseSerializer):
    response_set = serializers.SerializerMethodField()
    
    def get_response_set(self, obj):
        current_user = self.context.get('request', None).user
        question_id = self.context.get('kwargs', None).get('pk')
        responses = Response.objects.filter(question__id=question_id, author=current_user).order_by('-created_at')
        return ResponseSerializer(responses, many=True, read_only=True, context=self.context).data
    
    class Meta(QuestionBaseSerializer.Meta):
        model = Question
        fields = QuestionBaseSerializer.Meta.fields + ['response_set']


class QuestionFriendSerializer(QuestionBaseSerializer):
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = UserMinimalSerializer(source='author', read_only=True)

    class Meta(QuestionBaseSerializer.Meta):
        model = Question
        fields = QuestionBaseSerializer.Meta.fields + \
                 ['author', 'author_detail']


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


class QuestionDetailFriendResponsesSerializer(QuestionFriendSerializer):
    """
    for question detail page w/ friend responses
    """
    max_page = serializers.SerializerMethodField(read_only=True)
    response_set = serializers.SerializerMethodField()

    def get_max_page(self, obj):
        page_size = self.context['request'].query_params.get('size') or 15
        return obj.response_set.count() // page_size + 1

    def get_response_set(self, obj):
        current_user = self.context.get('request', None).user
        responses = obj.response_set.filter(author_id__in=current_user.connected_user_ids) | \
                    obj.response_set.filter(author_id=current_user.id)
        page_size = self.context['request'].query_params.get('size') or 15
        paginator = Paginator(responses, page_size)
        page = self.context['request'].query_params.get('page') or 1
        responses = paginator.page(page)
        return ResponseSerializer(responses, many=True, read_only=True, context=self.context).data

    class Meta(QuestionFriendSerializer.Meta):
        model = Question
        fields = QuestionFriendSerializer.Meta.fields + ['max_page', 'response_set']


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
        seven_days_ago = timezone.now() - timedelta(days=7)
        return obj.created_at >= seven_days_ago

    class Meta():
        model = ResponseRequest
        fields = ['id', 'requester_id', 'requestee_id', 'question_id', 'message', 'created_at', 'is_recent']


class ReceivedResponseRequestSerializer(ResponseRequestSerializer):
    requester_username = serializers.SerializerMethodField(read_only=True)
    question_content = serializers.SerializerMethodField(read_only=True)

    def get_requester_username(self, obj):
        return User.objects.get(id=obj.requester_id).username

    def get_question_content(self, obj):
        return Question.objects.get(id=obj.question_id).content

    class Meta:
        model = ResponseRequest
        fields = ResponseRequestSerializer.Meta.fields + ['requester_username', 'question_content']