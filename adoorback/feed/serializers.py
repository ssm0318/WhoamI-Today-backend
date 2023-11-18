from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from rest_framework import serializers
from rest_framework.exceptions import NotAcceptable
from django.urls import reverse

from account.models import FriendGroup
from account.serializers import AuthorFriendSerializer, AuthorAnonymousSerializer, UserFriendGroupBaseSerializer
from adoorback.serializers import AdoorBaseSerializer
from django.conf import settings
from adoorback.utils.content_types import get_generic_relation_type
from comment.serializers import CommentFriendSerializer, CommentResponsiveSerializer, CommentAnonymousSerializer
from feed.models import Article, Response, Question, Post, ResponseRequest
from like.models import Like
from reaction.serializers import ReactionMineSerializer

User = get_user_model()


class PostFriendSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = '__all__'

    def to_representation(self, obj):
        if isinstance(obj.target, Article):
            self.Meta.model = Article
            return ArticleFriendSerializer(obj.target, context=self.context).to_representation(obj.target)
        elif isinstance(obj.target, Response):
            self.Meta.model = Response
            return ResponseFriendSerializer(obj.target, context=self.context).to_representation(obj.target)
        raise NotAcceptable(detail=None, code=404)


class PostAnonymousSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = '__all__'

    def to_representation(self, obj):
        if isinstance(obj.target, Article):
            self.Meta.model = Article
            return ArticleAnonymousSerializer(obj.target, context=self.context).to_representation(obj.target)
        elif isinstance(obj.target, Response):
            self.Meta.model = Response
            return ResponseAnonymousSerializer(obj.target, context=self.context).to_representation(obj.target)
        raise NotAcceptable(detail=None, code=404)


class ArticleFriendSerializer(AdoorBaseSerializer):
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = AuthorFriendSerializer(source='author', read_only=True)
    comments = serializers.SerializerMethodField()

    def get_comments(self, obj):
        current_user = self.context.get('request', None).user
        comments = obj.article_comments.exclude(author_id__in=current_user.user_report_blocked_ids)
        if obj.author == current_user:
            comments = comments.order_by('is_anonymous', 'id')
            return CommentResponsiveSerializer(comments, many=True, read_only=True, context=self.context).data
        else: 
            comments = comments.filter(is_anonymous=False, is_private=False) | \
                       comments.filter(author=current_user, is_anonymous=False).order_by('id')
            return CommentFriendSerializer(comments, many=True, read_only=True, context=self.context).data

    class Meta(AdoorBaseSerializer.Meta):
        model = Article
        fields = AdoorBaseSerializer.Meta.fields + ['share_with_friends', 'share_anonymously',
                                                    'author', 'author_detail', 'comments']


class ArticleAnonymousSerializer(AdoorBaseSerializer):
    comments = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = serializers.SerializerMethodField(
        source='author', read_only=True)

    def get_author_detail(self, obj):
        if obj.author == self.context.get('request', None).user:
            return AuthorFriendSerializer(obj.author).data
        return AuthorAnonymousSerializer(obj.author).data

    def get_author(self, obj):
        if obj.author == self.context.get('request', None).user:
            return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})
        return None

    def get_comments(self, obj):
        current_user = self.context.get('request', None).user
        comments = obj.article_comments.exclude(author_id__in=current_user.user_report_blocked_ids)
        if obj.author == current_user:
            comments = comments.order_by('-is_anonymous', 'id')
            return CommentResponsiveSerializer(comments, many=True, read_only=True, context=self.context).data
        else:
            comments = comments.filter(is_anonymous=True, is_private=False) | \
                       comments.filter(author=current_user, is_anonymous=True).order_by('id')
            return CommentAnonymousSerializer(comments, many=True, read_only=True, context=self.context).data

    class Meta(AdoorBaseSerializer.Meta):
        model = Article
        fields = AdoorBaseSerializer.Meta.fields + ['share_with_friends', 'share_anonymously',
                                                    'author', 'author_detail', 'comments']


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


class ResponseMinimumSerializer(serializers.ModelSerializer):
    question = QuestionMinimumSerializer(read_only=True)
    current_user_like_id = serializers.SerializerMethodField(read_only=True)
    current_user_read = serializers.SerializerMethodField(read_only=True)

    def get_current_user_like_id(self, obj):
        current_user_id = self.context['request'].user.id
        content_type_id = get_generic_relation_type(obj.type).id
        like = Like.objects.filter(user_id=current_user_id, content_type_id=content_type_id, object_id=obj.id)
        return like[0].id if like else None
    
    def get_current_user_read(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.reader_ids

    class Meta(AdoorBaseSerializer.Meta):
        model = Response
        fields = ['id', 'type', 'content', 'current_user_like_id', 'question', 'date', 'available_limit', 
                  'created_at', 'current_user_read']


class ResponseBaseSerializer(AdoorBaseSerializer):
    question = QuestionBaseSerializer(read_only=True)
    question_id = serializers.IntegerField()
    current_user_read = serializers.SerializerMethodField(read_only=True)
    share_groups = serializers.ListField(child=serializers.IntegerField(), write_only=True)
    share_groups_details = UserFriendGroupBaseSerializer(source='share_groups', read_only=True, many=True)
    share_friends = serializers.ListField(child=serializers.IntegerField(), write_only=True)
    share_friends_details = AuthorFriendSerializer(source='share_friends', read_only=True, many=True)
    reaction_preview = serializers.SerializerMethodField(read_only=True)

    def get_reaction_preview(self, obj):
        current_user = self.context['request'].user
        reactions = obj.response_reactions.all().order_by('-created_at') if obj.author == current_user else \
            obj.response_reactions.filter(user_id=current_user.id).order_by('-created_at')

        if len(reactions) <= 4:
            return ReactionMineSerializer(reactions, many=True, read_only=True, context=self.context).data

        reactions_summary = list(reactions[:3]) + list(reactions[len(reactions) - 1:])
        return ReactionMineSerializer(reactions_summary, many=True, read_only=True, context=self.context).data

    def get_current_user_read(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.reader_ids
    
    class Meta(AdoorBaseSerializer.Meta):
        model = Response
        fields = AdoorBaseSerializer.Meta.fields + ['question', 'question_id', 'date', 'available_limit', 'current_user_read',
                                                    'reaction_preview', 'share_friends', 'share_friends_details', 
                                                    'share_groups', 'share_groups_details', 'share_everyone']


class ResponseFriendSerializer(ResponseBaseSerializer):
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = AuthorFriendSerializer(source='author', read_only=True)

    class Meta(ResponseBaseSerializer.Meta):
        model = Response
        fields = ResponseBaseSerializer.Meta.fields + \
                 ['author', 'author_detail']


class ResponseAnonymousSerializer(ResponseBaseSerializer):
    comments = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = serializers.SerializerMethodField(
        source='author', read_only=True)

    def get_author_detail(self, obj):
        if obj.author == self.context.get('request', None).user:
            return AuthorFriendSerializer(obj.author).data
        return AuthorAnonymousSerializer(obj.author).data

    def get_author(self, obj):
        if obj.author == self.context.get('request', None).user:
            return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})
        return None

    def get_comments(self, obj):
        current_user = self.context.get('request', None).user
        comments = obj.response_comments.exclude(author_id__in=current_user.user_report_blocked_ids)
        if obj.author == current_user:
            comments = comments.order_by('-is_anonymous', 'id')
            return CommentResponsiveSerializer(comments, many=True, read_only=True, context=self.context).data
        else:
            comments = comments.filter(is_anonymous=True, is_private=False) | \
                       comments.filter(author=current_user, is_anonymous=True).order_by('id')
            return CommentAnonymousSerializer(comments, many=True, read_only=True, context=self.context).data

    class Meta(ResponseBaseSerializer.Meta):
        model = Response
        fields = ResponseBaseSerializer.Meta.fields + ['author', 'author_detail', 'comments']


class ResponseResponsiveSerializer(ResponseBaseSerializer):
    comments = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = serializers.SerializerMethodField(
        source='author', read_only=True)

    def get_author_detail(self, obj):
        current_user = self.context.get('request', None).user
        if obj.share_with_friends and (User.are_friends(current_user, obj.author) or obj.author == current_user):
            return AuthorFriendSerializer(obj.author).data
        return AuthorAnonymousSerializer(obj.author).data

    def get_author(self, obj):
        current_user = self.context.get('request', None).user
        if obj.share_with_friends and (User.are_friends(current_user, obj.author) or obj.author == current_user):
            return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})
        return None

    def get_comments(self, obj):
        current_user = self.context.get('request', None).user
        comments = obj.response_comments.exclude(author_id__in=current_user.user_report_blocked_ids)
        if obj.author == current_user:
            comments = comments.order_by('-is_anonymous', 'id')
            return CommentResponsiveSerializer(comments, many=True, read_only=True, context=self.context).data
        elif obj.share_with_friends and User.are_friends(current_user, obj.author):
            comments = comments.filter(is_anonymous=False, is_private=False) | \
                       comments.filter(author=current_user, is_anonymous=False).order_by('id')
            return CommentFriendSerializer(comments, many=True, read_only=True, context=self.context).data
        else:
            comments = comments.filter(is_anonymous=True, is_private=False) | \
                       comments.filter(author=current_user, is_anonymous=True).order_by('id')
            return CommentAnonymousSerializer(comments, many=True, read_only=True, context=self.context).data

    class Meta(ResponseBaseSerializer.Meta):
        model = Article
        fields = ResponseBaseSerializer.Meta.fields + ['comments', 'author', 'author_detail']


class QuestionResponseSerializer(QuestionBaseSerializer):
    response_set = serializers.SerializerMethodField()
    
    def get_response_set(self, obj):
        current_user = self.context.get('request', None).user
        question_id = self.context.get('kwargs', None).get('pk')
        responses = Response.objects.filter(question__id=question_id, author=current_user).order_by('-created_at')
        return ResponseBaseSerializer(responses, many=True, read_only=True, context=self.context).data
    
    class Meta(QuestionBaseSerializer.Meta):
        model = Question
        fields = QuestionBaseSerializer.Meta.fields + ['response_set']


class QuestionResponsiveSerializer(QuestionBaseSerializer):
    """
    for questions in question feed (no responses, author profile responsive)
    """
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = serializers.SerializerMethodField(
        source='author', read_only=True)

    def get_author_detail(self, obj):
        current_user = self.context.get('request', None).user
        if User.are_friends(current_user, obj.author) or obj.author == current_user:
            return AuthorFriendSerializer(obj.author).data
        return AuthorAnonymousSerializer(obj.author).data

    def get_author(self, obj):
        if User.are_friends(self.context.get('request', None).user, obj.author):
            return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})
        return None

    class Meta(QuestionBaseSerializer.Meta):
        model = Question
        fields = QuestionBaseSerializer.Meta.fields + \
                 ['author', 'author_detail']


class QuestionFriendSerializer(QuestionBaseSerializer):
    """
    for questions in friend feed (no responses)

    function is redundant to `QuestionResponsiveSerializer`
    but allows for faster responses when rendering friend/anonymous feeds.
    """
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = AuthorFriendSerializer(source='author', read_only=True)

    class Meta(QuestionBaseSerializer.Meta):
        model = Question
        fields = QuestionBaseSerializer.Meta.fields + \
                 ['author', 'author_detail']


class DailyQuestionSerializer(QuestionBaseSerializer):
    """
    for questions in question feed

    (all profiles are anonymized, including that of the current user)
    """
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = serializers.SerializerMethodField(
        source='author', read_only=True)

    def get_author_detail(self, obj):
        return AuthorAnonymousSerializer(obj.author).data

    def get_author(self, obj):
        return None

    class Meta(QuestionBaseSerializer.Meta):
        model = Question
        fields = QuestionBaseSerializer.Meta.fields + ['author', 'author_detail']


class QuestionAnonymousSerializer(QuestionBaseSerializer):
    """
    for questions in anonymous feed (no responses)

    function is redundant to `QuestionResponsiveSerializer`
    but allows for faster responses when rendering friend/anonymous feeds.
    """
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = serializers.SerializerMethodField(
        source='author', read_only=True)

    def get_author_detail(self, obj):
        if obj.author == self.context.get('request', None).user:
            return AuthorFriendSerializer(obj.author).data
        return AuthorAnonymousSerializer(obj.author).data

    def get_author(self, obj):
        if obj.author == self.context.get('request', None).user:
            return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})
        return None

    class Meta(QuestionBaseSerializer.Meta):
        model = Question
        fields = QuestionBaseSerializer.Meta.fields + ['author', 'author_detail']


class QuestionDetailFriendResponsesSerializer(QuestionResponsiveSerializer):
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
        responses = obj.response_set.filter(author_id__in=current_user.friend_ids) | \
                    obj.response_set.filter(author_id=current_user.id)
        page_size = self.context['request'].query_params.get('size') or 15
        paginator = Paginator(responses, page_size)
        page = self.context['request'].query_params.get('page') or 1
        responses = paginator.page(page)
        return ResponseFriendSerializer(responses, many=True, read_only=True, context=self.context).data

    class Meta(QuestionResponsiveSerializer.Meta):
        model = Question
        fields = QuestionResponsiveSerializer.Meta.fields + ['max_page', 'response_set']


class QuestionDetailAnonymousResponsesSerializer(QuestionResponsiveSerializer):
    """
    for question detail page w/ anonymous responses
    """
    max_page = serializers.SerializerMethodField(read_only=True)
    response_set = serializers.SerializerMethodField()

    def get_max_page(self, obj):
        page_size = self.context['request'].query_params.get('size') or 15
        return obj.response_set.count() // page_size + 1

    def get_response_set(self, obj):
        responses = obj.response_set.filter(share_anonymously=True)
        page_size = self.context['request'].query_params.get('size') or 15
        paginator = Paginator(responses, page_size)
        page = self.context['request'].query_params.get('page') or 1
        responses = paginator.page(page)
        return ResponseAnonymousSerializer(responses, many=True, read_only=True, context=self.context).data

    class Meta(QuestionResponsiveSerializer.Meta):
        model = Question
        fields = QuestionResponsiveSerializer.Meta.fields + ['max_page', 'response_set']


class ResponseRequestSerializer(serializers.ModelSerializer):
    requester_id = serializers.IntegerField()
    requestee_id = serializers.IntegerField()
    question_id = serializers.IntegerField()

    def validate(self, data):
        if data.get('requester_id') == data.get('requestee_id'):
            raise serializers.ValidationError('본인과는 친구가 될 수 없어요...')
        return data

    class Meta():
        model = ResponseRequest
        fields = ['id', 'requester_id', 'requestee_id', 'question_id']
