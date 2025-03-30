from collections import defaultdict, OrderedDict
from itertools import chain
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction, IntegrityError
from django.db.models import F, Value, CharField, Q
from django.shortcuts import get_object_or_404
from django.utils import translation, timezone
from rest_framework import generics, exceptions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response as DjangoResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from adoorback.utils.exceptions import ExistingResponseRequest, NoSuchQuestion, DeletedQuestion
from adoorback.utils.permissions import IsAuthorOrReadOnly, IsShared, IsNotBlocked
from adoorback.utils.validators import adoor_exception_handler
import comment.serializers as cs
import qna.serializers as qs
from like.serializers import InteractionSerializer
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


class ResponseDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = qs.ResponseSerializer
    permission_classes = [IsAuthenticated, IsAuthorOrReadOnly, IsShared, IsNotBlocked]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        from adoorback.settings import LANGUAGES
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            raw_lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            lang_code = raw_lang.split(",")[0].split("-")[0].strip().lower()  # ex: "en-US" → "en"

            if lang_code in dict(LANGUAGES):
                translation.activate(lang_code)

        try:
            response = Response.objects.get(id=self.kwargs.get('pk'))
            self.check_object_permissions(self.request, response)
            if not response.is_audience(self.request.user):
                raise PermissionDenied("Sorry, you do not have permission to view this response.")
        except Response.DoesNotExist:
            raise exceptions.NotFound("Response not found")
        return response

    def get_queryset(self):
        from adoorback.settings import LANGUAGES
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            raw_lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            lang_code = raw_lang.split(",")[0].split("-")[0].strip().lower()  # ex: "en-US" → "en"

            if lang_code in dict(LANGUAGES):
                translation.activate(lang_code)

        queryset = Response.objects.all()
        return queryset

    def patch(self, request, *args, **kwargs):
        if 'visibility' in request.data:
            return self.partial_update(request, *args, **kwargs)
        return super().patch(request, *args, **kwargs)


class ResponseComments(generics.ListAPIView):
    serializer_class = cs.CommentFriendSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        from comment.models import Comment
        from content_report.models import ContentReport

        current_user = self.request.user
        
        response_ = get_object_or_404(Response, id=self.kwargs.get('pk'))
        if not response_.is_audience(current_user):
            raise PermissionDenied("You do not have permission to view these comments.")
        
        blocked_content_ids = ContentReport.objects.filter(
            user=current_user,
            content_type=ContentType.objects.get_for_model(Comment)
        ).values_list('object_id', flat=True)

        return response_.response_comments.exclude(
            Q(id__in=blocked_content_ids) | Q(author_id__in=current_user.user_report_blocked_ids)
        ).order_by('created_at')

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


class ResponseInteractions(generics.ListAPIView):
    serializer_class = InteractionSerializer
    permission_classes = [IsAuthenticated, IsAuthorOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        from like.models import Like
        from reaction.models import Reaction

        response_id = self.kwargs['pk']
        response = Response.objects.get(pk=response_id)

        if not response.is_audience(self.request.user):
            raise PermissionDenied("You do not have permission to view likes on this response.")

        likes = Like.objects.filter(content_type__model='response', object_id=response_id).annotate(
            reaction=Value(None, output_field=CharField())
        )

        reactions = Reaction.objects.filter(content_type__model='response', object_id=response_id).annotate(
            reaction=F('emoji')
        )

        combined_interactions = sorted(
            chain(likes, reactions),
            key=lambda x: x.created_at,
            reverse=True
        )

        return combined_interactions


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


class DateGroupPagination(PageNumberPagination):
    page_size = 2  # paginate by 2 dates


class QuestionList(generics.ListCreateAPIView):
    serializer_class = qs.QuestionBaseSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request, *args, **kwargs):
        from adoorback.settings import LANGUAGES
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            raw_lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            lang_code = raw_lang.split(",")[0].split("-")[0].strip().lower()  # ex: "en-US" → "en"

            if lang_code in dict(LANGUAGES):
                translation.activate(lang_code)

        # get 30 recent questions excluding future questions
        user = request.user
        try:
            tz = ZoneInfo(user.timezone)
        except Exception:
            tz = ZoneInfo("America/Los_Angeles")
        today = timezone.now().astimezone(tz).date()
        daily_questions = list(Question.objects.daily_questions(request.user))  # DailyQuestionList와 순서 일치를 위해
        excluded_ids = tuple(q.id for q in daily_questions)
        excluded_clause = "AND id NOT IN %s" if excluded_ids else ""
        sql = f"""
            SELECT * FROM qna_question
            WHERE array_length(selected_dates, 1) IS NOT NULL
            AND selected_dates[array_upper(selected_dates, 1)] <= %s
            {excluded_clause}
            ORDER BY selected_dates[array_upper(selected_dates, 1)] DESC
            LIMIT 30;
        """
        params = [today]
        if excluded_ids:
            params.append(excluded_ids)
        
        queryset = list(Question.objects.raw(sql, params))
        all_questions = daily_questions + queryset

        # group by date
        grouped = defaultdict(list)
        for question in all_questions:
            if question.selected_dates:
                last_date = question.selected_dates[-1]
                grouped[last_date].append(question)

        grouped_ordered = OrderedDict(
            sorted(grouped.items(), key=lambda x: x[0], reverse=True)
        )

        grouped_list = [
            {"date": str(date), "questions": questions}
            for date, questions in grouped_ordered.items()
        ]

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(grouped_list, request)

        serialized_data = []
        for group in page:
            serialized_group = {
                "date": group["date"],
                "questions": self.serializer_class(
                    group["questions"], many=True, context={"request": request}
                ).data
            }
            serialized_data.append(serialized_group)

        return paginator.get_paginated_response(
            qs.QuestionGroupSerializer(serialized_data, many=True).data
        )


    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class QuestionDetail(generics.RetrieveAPIView):
    serializer_class = qs.QuestionBaseSerializer
    permission_classes = [IsAuthenticated, IsAuthorOrReadOnly, IsShared, IsNotBlocked]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        from adoorback.settings import LANGUAGES
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            raw_lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            lang_code = raw_lang.split(",")[0].split("-")[0].strip().lower()  # ex: "en-US" → "en"

            if lang_code in dict(LANGUAGES):
                translation.activate(lang_code)

        queryset = Question.objects.all()
        return queryset


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
        if not requestee.is_connected(current_user):
            raise PermissionDenied("친구에게만 response request를 보낼 수 있습니다.")
        try:
            serializer.save()
        except IntegrityError as e:
            if 'unique constraint' in e.args[0]:
                raise ExistingResponseRequest()
            else:
                raise e


class DailyQuestionList(generics.ListAPIView):
    serializer_class = qs.DailyQuestionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        from adoorback.settings import LANGUAGES
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            raw_lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            lang_code = raw_lang.split(",")[0].split("-")[0].strip().lower()  # ex: "en-US" → "en"

            if lang_code in dict(LANGUAGES):
                translation.activate(lang_code)

        return Question.objects.daily_questions(self.request.user)
