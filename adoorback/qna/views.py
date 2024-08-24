import os
import pandas as pd
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction, IntegrityError
from django.http import HttpResponseBadRequest
from django.utils import translation
from django.db.models import Max
from django.core.exceptions import ValidationError
from rest_framework import generics, exceptions, status
from rest_framework.response import Response as DjangoResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from adoorback.utils.exceptions import ExistingResponseRequest, NoSuchQuestion, DeletedQuestion
from adoorback.utils.permissions import IsAuthorOrReadOnly, IsShared, IsNotBlocked
from adoorback.utils.validators import adoor_exception_handler
import comment.serializers as cs
import qna.serializers as qs
from like.serializers import LikeSerializer
from qna.models import Response, Question, ResponseRequest

User = get_user_model()


class ResponseCreate(generics.CreateAPIView):
    serializer_class = qs.ResponseSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class QuestionResponseList(generics.RetrieveAPIView):
    serializer_class = qs.QuestionResponseSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        return {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self,
            'kwargs': self.kwargs,
        }

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        queryset = Question.objects.all()
        return queryset

    def get_exception_handler(self):
        return adoor_exception_handler


class ResponseDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = qs.ResponseSerializer
    permission_classes = [IsAuthenticated, IsAuthorOrReadOnly, IsShared, IsNotBlocked]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        try:
            response = Response.objects.get(id=self.kwargs.get('pk'))
            self.check_object_permissions(self.request, response)
        except Response.DoesNotExist:
            raise exceptions.NotFound("Response not found")
        return response

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        queryset = Response.objects.all()
        return queryset


class ResponseComments(generics.ListAPIView):
    serializer_class = cs.CommentFriendSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        from comment.models import Comment
        from content_report.models import ContentReport

        current_user = self.request.user
        
        response_ = Response.objects.get(id=self.kwargs.get('pk'))
        if not response_.is_audience(current_user):
            raise PermissionDenied("You do not have permission to view these comments.")
        
        blocked_content_ids = ContentReport.objects.filter(
            user=current_user,
            content_type=ContentType.objects.get_for_model(Comment)
        ).values_list('object_id', flat=True)

        return response_.response_comments.exclude(
            id__in=blocked_content_ids,
            author_id__in=current_user.user_report_blocked_ids
        ).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        comments = self.get_queryset()
        current_user = self.request.user

        all_comments_and_replies = comments
        for comment in comments:
            replies = comment.replies.exclude(author_id__in=current_user.user_report_blocked_ids)
            all_comments_and_replies = all_comments_and_replies.union(replies)

        page = self.paginate_queryset(comments)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            extra_field = {'count_including_replies': all_comments_and_replies.count()}
            paginated_response = self.get_paginated_response(serializer.data)
            paginated_response.data.update(extra_field)
            return paginated_response

        serializer = self.get_serializer(comments, many=True)
        extra_field = {'count_including_replies': all_comments_and_replies.count()}
        return Response({'results': serializer.data, **extra_field})


class ResponseLikes(generics.ListAPIView):
    serializer_class = LikeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from like.models import Like
        response_id = self.kwargs['pk']
        return Like.objects.filter(content_type__model='response', object_id=response_id)


class ResponseRead(generics.UpdateAPIView):
    queryset = Response.objects.all()
    serializer_class = qs.ResponseSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def patch(self, request, *args, **kwargs):
        current_user = self.request.user
        ids = request.data.get('ids', [])
        queryset = Response.objects.filter(id__in=ids)
        if len(ids) != queryset.count():
            return DjangoResponse({'error': 'Response with provided IDs does not exist.'},
                                  status=status.HTTP_404_NOT_FOUND)
        for response in queryset:
            response.readers.add(current_user)
        serializer = self.get_serializer(queryset, many=True)

        return DjangoResponse(serializer.data)


class QuestionList(generics.ListCreateAPIView):
    serializer_class = qs.QuestionBaseSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        queryset = Question.objects.raw("""
                SELECT * FROM qna_question
                WHERE array_length(selected_dates, 1) IS NOT NULL
                ORDER BY selected_dates[array_upper(selected_dates, 1)] DESC
                LIMIT 30;
            """)
        # exclude tomorrow's question if exists
        if queryset and queryset[0].selected_dates[-1] > date.today():
            queryset = queryset[1:]

        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class QuestionDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = qs.QuestionBaseSerializer
    permission_classes = [IsAuthenticated, IsAuthorOrReadOnly, IsShared, IsNotBlocked]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        queryset = Question.objects.all()
        return queryset


class ResponseRequestList(generics.ListAPIView):
    serializer_class = qs.ResponseRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        try:
            question = Question.objects.get(id=self.kwargs['qid'])
        except Question.DoesNotExist:
            return HttpResponseBadRequest
        sent_response_request_set = self.request.user.sent_response_request_set.all()
        response_requests = sent_response_request_set.filter(question=question).order_by('-id')
        return response_requests


class ResponseRequestCreate(generics.CreateAPIView):
    """
    Get response requests of the selected question.
    """
    queryset = ResponseRequest.objects.all()
    serializer_class = qs.ResponseRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        current_user = self.request.user
        requester = User.objects.get(id=self.request.data.get('requester_id'))
        requestee = User.objects.get(id=self.request.data.get('requestee_id'))
        question_id = self.request.data.get('question_id')
        if Question.all_objects.filter(id=question_id, deleted__isnull=False).exists():
            raise DeletedQuestion()
        if not Question.objects.filter(id=question_id).exists():
            raise NoSuchQuestion()
        if requester != current_user:
            raise PermissionDenied("requester가 본인이 아닙니다.")
        if not User.are_friends(requestee, current_user):
            raise PermissionDenied("친구에게만 response request를 보낼 수 있습니다.")
        try:
            serializer.save()
        except IntegrityError as e:
            if 'unique constraint' in e.args[0]:
                raise ExistingResponseRequest()
            else:
                raise e


class ResponseRequestDestroy(generics.DestroyAPIView):
    serializer_class = qs.ResponseRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        # since the requester is the authenticated user, no further permission checking unnecessary
        return ResponseRequest.objects.get(requester_id=self.request.user.id,
                                           requestee_id=self.kwargs.get('rid'),
                                           question_id=self.kwargs.get('qid'))


class DailyQuestionList(generics.ListAPIView):
    serializer_class = qs.DailyQuestionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        daily_questions = Question.objects.daily_questions()
        daily_questions = daily_questions.annotate(max_selected_date=Max('selected_dates'))
        return daily_questions.order_by('-max_selected_date')


class DateQuestionList(generics.ListAPIView):
    serializer_class = qs.DailyQuestionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')
        return Question.objects.date_questions(date=date(year=year, month=month, day=day))


class RecommendedQuestionList(generics.ListAPIView):
    serializer_class = qs.QuestionBaseSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        try:
            dir_name = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(dir_name, 'algorithms', 'recommendations.csv')
            df = pd.read_csv(path)
        except FileNotFoundError:
            return Question.objects.daily_questions().order_by('?')[:5]

        df = df[df.userId == self.request.user.id]
        rank_ids = df['questionId'].tolist()
        daily_question_ids = set(list(Question.objects.daily_questions().values_list('id', flat=True)))
        recommended_ids = [x for x in rank_ids if x in daily_question_ids][:5]
        recommended_ids = recommended_ids if len(recommended_ids) == 5 else \
            Question.objects.daily_questions().values_list('id', flat=True)[:5]

        return Question.objects.filter(pk__in=recommended_ids).order_by('?')
