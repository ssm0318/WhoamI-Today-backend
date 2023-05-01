import datetime

from test_plus.test import TestCase
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model

from comment.models import Comment
from feed.models import Article, Response, Question, Post, ResponseRequest
from notification.models import Notification

from adoorback.test.seed import set_seed, fill_data
from adoorback.utils.content_types import get_response_type

User = get_user_model()
N = 10


class FeedTestCase(TestCase):
    def setUp(self):
        set_seed(N)

    def test_feed_count(self):
        self.assertEqual(Article.objects.count(), N)
        self.assertEqual(Question.objects.admin_questions_only().count(), N)
        self.assertEqual(Question.objects.custom_questions_only().count(), N)
        self.assertLessEqual(Question.objects.daily_questions().count(), 30)
        self.assertEqual(Response.objects.count(), N)
        self.assertEqual(Post.objects.count(), N * 4)

    def test_feed_str(self):
        article = Article.objects.create(author_id=1, content="test_content")
        self.assertEqual(article.__str__(), article.content)

    # all feeds must be deleted along with user
    def test_on_delete_undelete_user_cascade(self):
        fill_data()
        user = User.objects.get(id=2)
        articles_cnt = user.article_set.all().count()
        responses_cnt = user.response_set.all().count()
        questions_cnt = user.question_set.all().count()
        self.assertGreater(articles_cnt, 0)
        self.assertGreater(responses_cnt, 0)
        self.assertGreater(questions_cnt, 0)

        user.delete()
        self.assertEqual(User.objects.filter(id=2).count(), 0)
        self.assertEqual(Article.objects.filter(author_id=2).count(), 0)
        self.assertEqual(Response.objects.filter(author_id=2).count(), 0)
        self.assertEqual(Question.objects.filter(author_id=2).count(), 0)

        # undelete
        user.undelete()
        self.assertEqual(User.objects.filter(id=2).count(), 1)
        self.assertEqual(Article.objects.filter(author_id=2).count(), articles_cnt)
        self.assertEqual(Response.objects.filter(author_id=2).count(), responses_cnt)
        self.assertEqual(Question.objects.filter(author_id=2).count(), questions_cnt)

    # response must be deleted along with question
    def test_on_delete_undelete_question_cascade(self):
        response = Response.objects.last()
        response_id = response.id
        question = response.question

        question.delete()
        self.assertEqual(Response.objects.filter(id=response_id).count(), 0)

        # undelete
        question.undelete()
        self.assertEqual(Response.objects.filter(id=response_id).count(), 1)

    # post content must change to reflect target content
    def test_post_update(self):
        response = Response.objects.last()
        response.content = "modified content"
        response.save()

        self.assertEqual(Post.objects.filter(content_type=get_response_type(),
                                             object_id=response.id).last().content, response.content)

    # post content must be removed along with target
    def test_post_delete_undelete(self):
        response = Response.objects.last()
        response_id = response.id
        posts_cnt = Post.objects.filter(object_id=response.id).count()
        response.delete()

        self.assertEqual(Post.objects.filter(content_type=get_response_type(), 
                                             object_id=response_id).count(), 0)

        # undelete
        response.undelete()
        self.assertEqual(Post.objects.filter(object_id=response.id).count(), posts_cnt)


class ResponseRequestTestCase(TestCase):
    def setUp(self):
        set_seed(N)

    def test_feed_str(self):
        response_request = ResponseRequest.objects.last()
        self.assertEqual(response_request.__str__(),
                         f'{response_request.requester} '
                         f'sent ({response_request.question}) '
                         f'to {response_request.requestee}')

    def test_response_request_count(self):
        self.assertGreater(ResponseRequest.objects.count(), 0)  # due to unique constraint

    def test_on_delete_undelete_actor_cascade(self):
        user = ResponseRequest.objects.first().requester
        sent_response_requests_cnt = user.sent_response_request_set.all().count()
        self.assertGreater(sent_response_requests_cnt, 0)

        user.delete()
        self.assertEqual(User.objects.filter(id=user.id).count(), 0)
        self.assertEqual(ResponseRequest.objects.filter(requester_id=user.id).count(), 0)
        self.assertEqual(ResponseRequest.objects.filter(requestee_id=user.id).count(), 0)

        # undelete
        user.undelete()
        self.assertEqual(User.objects.filter(id=user.id).count(), 1)
        self.assertEqual(ResponseRequest.objects.filter(requester_id=user.id).count(), sent_response_requests_cnt)

    def test_on_delete_undelete_recipient_cascade(self):
        user = ResponseRequest.objects.first().requestee
        received_response_requests_cnt = user.received_response_request_set.all().count()
        self.assertGreater(received_response_requests_cnt, 0)

        user.delete()
        self.assertEqual(User.objects.filter(id=user.id).count(), 0)
        self.assertEqual(ResponseRequest.objects.filter(requestee_id=user.id).count(), 0)
        self.assertEqual(ResponseRequest.objects.filter(requester_id=user.id).count(), 0)

        # undelete
        user.undelete()
        self.assertEqual(User.objects.filter(id=user.id).count(), 1)
        self.assertEqual(ResponseRequest.objects.filter(requestee_id=user.id).count(), received_response_requests_cnt)

    def test_on_delete_undelete_question_cascade(self):
        question = ResponseRequest.objects.first().question
        response_request_cnt = ResponseRequest.objects.filter(question_id=question.id).count()
        self.assertGreater(response_request_cnt, 0)

        question.delete()
        self.assertEqual(ResponseRequest.objects.filter(question_id=question.id).count(), 0)

        # undelete
        question.undelete()
        self.assertEqual(ResponseRequest.objects.filter(question_id=question.id).count(), response_request_cnt)


class APITestCase(TestCase):
    client_class = APIClient


class PostAPITestCase(APITestCase):

    def test_feed_permissions(self):
        current_user = self.make_user(username='current_user')
        friend_user = self.make_user(username='friend_user')
        friend_user.friends.add(current_user)

        question = Question.objects.create(author_id=current_user.id, content="test_question",
                                           is_admin_question=False)
        Response.objects.create(author_id=current_user.id, content="test_response",
                                question_id=question.id,
                                share_with_friends=True, share_anonymously=True)
        Article.objects.create(author_id=friend_user.id, content="test_article",
                               share_with_friends=False, share_anonymously=False)
        article = Article.objects.create(author_id=current_user.id, content="test_article",
                                         share_with_friends=True, share_anonymously=True)

        # Seed comments w/ different share settings
        comment_anonymous = Comment.objects.create(author_id=current_user.id, target=article,
                                                   content="test comment1", is_anonymous=True, is_private=True)
        Comment.objects.create(author_id=current_user.id, target=article,
                               content="test comment2", is_anonymous=True, is_private=False)
        Comment.objects.create(author_id=current_user.id, target=article,
                               content="test comment3", is_anonymous=False, is_private=True)
        comment_friend = Comment.objects.create(author_id=current_user.id, target=article,
                                                content="test comment4", is_anonymous=False, is_private=False)

        # Seed replies w/ different share settings
        Comment.objects.create(author_id=current_user.id, target=comment_friend,
                               content="test reply1", is_anonymous=False, is_private=True)
        Comment.objects.create(author_id=current_user.id, target=comment_friend,
                               content="test reply2", is_anonymous=False, is_private=False)
        Comment.objects.create(author_id=current_user.id, target=comment_anonymous,
                               content="test reply3", is_anonymous=True, is_private=True)
        Comment.objects.create(author_id=current_user.id, target=comment_anonymous,
                               content="test reply4", is_anonymous=True, is_private=False)

        # test friend feed - self
        with self.login(username=current_user.username, password='password'):
            response = self.get('friend-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 3)
            self.assertEqual(response.data['results'][0]['type'], 'Article')
            self.assertEqual(response.data['results'][1]['type'], 'Response')
            self.assertEqual(response.data['results'][2]['type'], 'Question')
            self.assertEqual(response.data['results'][0]['share_with_friends'], True)

            # test comments
            self.assertEqual(response.data['results'][0]['comments'][0]['is_reply'], False)
            self.assertEqual(len(response.data['results'][0]['comments']), 4)
            self.assertEqual(response.data['results'][0]['comments'][2]['replies'][0]['is_reply'], True)
            self.assertEqual(response.data['results'][0]['comments'][2]['replies'][0]['is_anonymous'], True)
            self.assertEqual(response.data['results'][0]['comments'][1]['replies'][0]['is_anonymous'], False)

        # test friend feed - friend
        with self.login(username=friend_user.username, password='password'):
            response = self.get('friend-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 4)
            self.assertEqual(response.data['results'][0]['type'], 'Article')

            # test comments
            self.assertEqual(len(response.data['results'][0]['comments']), 1)  # private/anonymous comments hidden
            self.assertEqual(len(response.data['results'][0]['comments'][0]['replies']), 1)

        # test anonymous feed - self
        with self.login(username=current_user.username, password='password'):
            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.data['count'], 3)
            self.assertEqual(response.data['results'][0]['share_anonymously'], True)

            # test comments
            self.assertEqual(response.data['results'][0]['comments'][0]['is_anonymous'], True)
            self.assertEqual(response.data['results'][0]['comments'][3]['is_anonymous'], False)  # ordering
            self.assertEqual(len(response.data['results'][0]['comments']), 4)
            self.assertEqual(len(response.data['results'][0]['comments'][3]['replies']), 2)

        # test anonymous feed - friend
        with self.login(username=friend_user.username, password='password'):
            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 3)
            self.assertEqual(response.data['results'][0]['type'], 'Article')

            # test comments
            self.assertEqual(len(response.data['results'][0]['comments']), 1)  # private/anonymous comments hidden
            self.assertEqual(response.data['results'][0]['comments'][0]['is_anonymous'], True)
            self.assertEqual(len(response.data['results'][0]['comments'][0]['replies']), 0)


class UserFeedTestCase(APITestCase):

    def setUp(self):
        set_seed(N)

    def test_user_feed(self):
        current_user = self.make_user(username='current_user')
        friend_user = self.make_user(username='friend_user')

        fid = friend_user.id
        Question.objects.create(author_id=fid, content="test_question", is_admin_question=False)
        Response.objects.create(author_id=fid, content="test_response", question_id=1)
        Article.objects.create(author_id=fid, content="test_article")
        Article.objects.create(author_id=fid, content="test_article", share_with_friends=False)

        # user feed of friend
        current_user.friends.add(friend_user)
        with self.login(username=current_user.username, password='password'):
            response = self.get(self.reverse('user-feed-post-list', pk=friend_user.id))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 3)

        # user feed of non-friend
        with self.login(username=current_user.username, password='password'):
            response = self.get(self.reverse('user-feed-post-list', pk=1))
            self.assertEqual(response.status_code, 403)


class ArticleAPITestCase(APITestCase):

    def test_restrictions(self):
        current_user = self.make_user(username='current_user')
        spy_user = self.make_user(username='spy_user')

        with self.login(username=current_user.username, password='password'):
            data = {"content": "test content", "share_anonymously": True}
            response = self.post('article-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        article_id = Article.objects.last().id
        data = {"content": "modified content"}
        with self.login(username=current_user.username, password='password'):
            response = self.patch(self.reverse('article-detail', pk=article_id),
                                  data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)

        with self.login(username=spy_user.username, password='password'):
            response = self.patch(self.reverse('article-detail', pk=article_id),
                                  data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 403)

        # anonymous
        with self.login(username=spy_user.username, password='password'):
            response = self.get(self.reverse('article-detail', pk=article_id))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data['author_detail']), 1)


class QuestionAPITestCase(APITestCase):

    def test_restrictions(self):
        current_user = self.make_user(username='current_user')
        spy_user = self.make_user(username='spy_user')

        # seed
        with self.login(username=current_user.username, password='password'):
            data = {"content": "test content", "is_admin_question": True}
            response = self.post('question-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        question_id = Question.objects.last().id

        data = {"content": "modified content"}
        with self.login(username=current_user.username, password='password'):
            response = self.patch(self.reverse('question-detail', pk=question_id),
                                  data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)

        # not allowed
        with self.login(username=spy_user.username, password='password'):
            response = self.patch(self.reverse('question-detail', pk=question_id),
                                  data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 403)

    def test_question_detail(self):
        current_user = self.make_user(username='current_user')
        spy_user = self.make_user(username='spy_user')

        # seed
        with self.login(username=current_user.username, password='password'):
            data = {"content": "test content", "is_admin_question": True}
            response = self.post('question-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        question_id = Question.objects.last().id
        with self.login(username=current_user.username, password='password'):
            data = {"content": "test content", "question_id": question_id,
                    "share_with_friends": True, "share_anonymously": True}
            response = self.post('response-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)
            data = {"content": "test content", "question_id": question_id,
                    "share_with_friends": True, "share_anonymously": False}
            response = self.post('response-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)
            data = {"content": "test content", "question_id": question_id,
                    "share_with_friends": False, "share_anonymously": True}
            response = self.post('response-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        # accessible question detail - anonymous
        with self.login(username=spy_user.username, password='password'):
            response = self.get(self.reverse('question-detail', pk=question_id))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data['response_set']), 2)
            self.assertEqual(len(response.data['author_detail']), 1)  # author anonymous

            # response type toggle
            response = self.get(self.reverse('question-detail-anonymous', pk=question_id))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data['response_set']), 2)
            response = self.get(self.reverse('question-detail-friend', pk=question_id))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data['response_set']), 0)

        # accessible question detail - friend
        with self.login(username=current_user.username, password='password'):
            response = self.get(self.reverse('question-detail', pk=question_id))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data['response_set']), 3)
            self.assertGreater(len(response.data['author_detail']), 1)  # author public

            # response type toggle
            response = self.get(self.reverse('question-detail-anonymous', pk=question_id))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data['response_set']), 2)
            response = self.get(self.reverse('question-detail-friend', pk=question_id))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data['response_set']), 3)


class ResponseAPITestCase(APITestCase):

    def test_restrictions(self):
        current_user = self.make_user(username='current_user')
        spy_user = self.make_user(username='spy_user')

        with self.login(username=current_user.username, password='password'):
            question = Question.objects.create(author_id=1, content="test_question", is_admin_question=False)
            data = {"content": "test content", "question_id": question.id, "share_anonymously": True}
            response = self.post('response-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.data['question_id'], Response.objects.last().question_id)

        response_id = Response.objects.last().id
        data = {"content": "modified content"}
        with self.login(username=current_user.username, password='password'):
            response = self.patch(self.reverse('response-detail', pk=response_id),
                                  data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['question_id'], Question.objects.last().id)

        with self.login(username=spy_user.username, password='password'):
            response = self.patch(self.reverse('response-detail', pk=response_id),
                                  data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 403)

        # anonymous author profile in detail page
        with self.login(username=spy_user.username, password='password'):
            response = self.get(self.reverse('response-detail', pk=response_id))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data['author_detail']), 1)
            self.assertEqual(response.data['question_id'], Question.objects.last().id)


class DailyQuestionTestCase(APITestCase):

    def test_daily_questions_call(self):
        current_user = self.make_user(username='current_user')

        for _ in range(50):
            Question.objects.create(author_id=1, content="test_question", is_admin_question=False)

        with self.login(username=current_user.username, password='password'):
            response = self.get('daily-question-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data), 30)
            self.assertTrue(response.data[1]['selected_date'])

    def test_recommended_questions_call(self):
        current_user = self.make_user(username='current_user')

        for _ in range(50):
            Question.objects.create(author_id=1, content="test_question", is_admin_question=False)

        with self.login(username=current_user.username, password='password'):
            response = self.get('daily-question-list')
            self.assertEqual(response.status_code, 200)
            response = self.get('recommended-question-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 5)
            self.assertIn(datetime.date.today().strftime("%Y-%m-%d"),
                          response.data['results'][1]['selected_date'])
            self.assertIn(datetime.date.today().strftime("%Y-%m-%d"),
                          response.data['results'][1]['selected_date'])


class ResponseRequestAPITestCase(APITestCase):

    def setUp(self):
        set_seed(N)

    def test_response_request_list(self):
        current_user = self.make_user(username='current_user')
        friend_user_1 = self.make_user(username='friend_user_1')
        friend_user_2 = self.make_user(username='friend_user_2')

        question_1 = Question.objects.create(author_id=current_user.id,
                                             content="test_question", is_admin_question=False)
        question_2 = Question.objects.create(author_id=current_user.id,
                                             content="test_question", is_admin_question=False)

        prev_noti_count = Notification.objects.count()
        ResponseRequest.objects.create(requester=current_user, requestee=friend_user_1, question=question_1)
        ResponseRequest.objects.create(requester=current_user, requestee=friend_user_2, question=question_2)
        ResponseRequest.objects.create(requester=friend_user_1, requestee=friend_user_2, question=question_1)
        curr_noti_count = Notification.objects.count()
        self.assertGreater(curr_noti_count, prev_noti_count)

        with self.login(username=current_user.username, password='password'):
            response = self.get(self.reverse('response-request-list', qid=question_1.id))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data), 1)

    def test_response_request_detail(self):
        current_user = self.make_user(username='current_user')
        friend_user = self.make_user(username='friend_user')
        user_adoor = User.objects.get(username='adoor')

        question = Question.objects.create(author_id=current_user.id, content="test_question", is_admin_question=False)
        ResponseRequest.objects.create(requester=friend_user, requestee=current_user, question=question)
        current_user.friends.add(friend_user)

        # POST - send response request to friend
        data = {"requester_id": current_user.id, "requestee_id": friend_user.id, "question_id": question.id}
        with self.login(username=current_user.username, password='password'):
            response = self.post('response-request-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        # POST - send response request to non-friend (not allowed)
        data = {"requester_id": user_adoor.id, "requestee_id": current_user.id, "question_id": question.id}
        with self.login(username=user_adoor.username, password='adoor2020:)'):
            response = self.post('response-request-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 403)

        # POST - send response request as someone else (not allowed)
        data = {"requester_id": user_adoor.id, "requestee_id": current_user.id, "question_id": question.id}
        with self.login(username=friend_user.username, password='password'):
            response = self.post('response-request-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 403)

        adoor_received_response_request = ResponseRequest.objects.create(requester=current_user,
                                                                         requestee=user_adoor, question=question)
        qid = adoor_received_response_request.question.id
        rid = user_adoor.id

        # DELETE - actor
        with self.login(username=current_user.username, password='password'):
            response = self.delete(self.reverse('response-request-destroy',
                                                qid=question.id, rid=friend_user.id))
            self.assertEqual(response.status_code, 204)

        # GET - method not allowed
        with self.login(username=current_user.username, password='password'):
            response = self.get(self.reverse('response-request-destroy', qid=qid, rid=rid))
            self.assertEqual(response.status_code, 405)

        # PATCH - method not allowed
        with self.login(username=current_user.username, password='password'):
            response = self.patch(self.reverse('response-request-destroy', qid=qid, rid=rid))
            self.assertEqual(response.status_code, 405)


class ResponseRequestNotiAPITestCase(APITestCase):

    def setUp(self):
        set_seed(N)

    def test_response_request_noti(self):
        current_user = self.make_user(username='current_user')
        friend_user = self.make_user(username='friend_user')

        question = Question.objects.create(author_id=current_user.id,
                                           content="test_question", is_admin_question=False)

        # POST - send response request (current_user -> friend_user)
        data = {"requester_id": current_user.id, "requestee_id": friend_user.id, "question_id": question.id}
        with self.login(username=current_user.username, password='password'):
            num_noti_before = Notification.objects.count()
            # requester - requestee must be friends
            current_user.friends.add(friend_user)
            response = self.post('response-request-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            num_noti_after = Notification.objects.count()
            self.assertEqual(num_noti_after, num_noti_before + 1)
            response_request_noti = Notification.objects.first()
            self.assertEqual(response_request_noti.user, friend_user)
            self.assertEqual(response_request_noti.actor, current_user)
            self.assertEqual(response_request_noti.message_ko, "똑똑똑~ current_user님으로부터 질문이 왔어요!")
            self.assertEqual(response_request_noti.redirect_url, f'/questions/{question.id}')

        # mutliple response requests to a user on a question
        random_user_1 = self.make_user(username='random_user_1')
        random_user_2 = self.make_user(username='random_user_2')
        random_user_3 = self.make_user(username='random_user_3')
        friend_user.friends.add(random_user_1, random_user_2, random_user_3)  # must be friends

        data = {"requester_id": random_user_1.id, "requestee_id": friend_user.id, "question_id": question.id}
        with self.login(username=random_user_1.username, password='password'):
            response = self.post('response-request-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        data = {"requester_id": random_user_2.id, "requestee_id": friend_user.id, "question_id": question.id}
        with self.login(username=random_user_2.username, password='password'):
            response = self.post('response-request-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        data = {"requester_id": random_user_3.id, "requestee_id": friend_user.id, "question_id": question.id}
        with self.login(username=random_user_3.username, password='password'):
            response = self.post('response-request-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        # POST - response to response request
        # (requesters: current_user, random_user_1, random_user_2, random_user_3)
        with self.login(username=friend_user.username, password='password'):
            num_noti_before = Notification.objects.count()
            data = {"content": "test content", "question_id": question.id, "share_anonymously": True}
            response = self.post('response-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            num_noti_after = Notification.objects.count()
            self.assertEqual(num_noti_before, num_noti_after)  # 4개의 답변 관련 노티 생성, 4개의 요청 관련 노티 삭제 -> 변화 X

            self.assertEqual(Response.objects.first().response_targetted_notis.count(), 4)  # 요청자 각각에게
            self.assertEqual(Notification.objects.first().user, random_user_3)
            self.assertEqual(Notification.objects.first().message_ko, 'friend_user님이 회원님이 보낸 질문에 답했습니다.')

        # PATCH - modifying response should not create a new notification
        response_id = Response.objects.first().id
        data = {"content": "modified content"}
        with self.login(username=friend_user.username, password='password'):
            num_noti_before = Notification.objects.count()
            response = self.patch(self.reverse('response-detail', pk=response_id),
                                  data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)

            num_noti_after = Notification.objects.count()
            self.assertEqual(num_noti_before, num_noti_after)


class ExceptionHandlerAPITestCase(APITestCase):

    def setUp(self):
        set_seed(N)

    def test_exception_raised(self):
        response = self.get('friend-feed-post-list')
        self.assertEqual(response.status_code, 403)

        response = self.get('anonyous-feed-post-list')
        self.assertEqual(response.status_code, 404)

        data = {"content": "test content", "share_anonymously": True}
        response = self.post('article-list', data=data, extra={'format': 'json'})
        self.assertEqual(response.status_code, 403)

        response = self.get('response-list')
        self.assertEqual(response.status_code, 403)

        response = self.get('question-list')
        self.assertEqual(response.status_code, 403)

        response = self.get(self.reverse('question-detail-friend', pk=1))
        self.assertEqual(response.status_code, 403)

        response = self.get(self.reverse('question-detail-anonymous', pk=1))
        self.assertEqual(response.status_code, 403)

        response = self.get(self.reverse('response-request-list', qid=0))
        self.assertEqual(response.status_code, 403)

        response = self.get('daily-question-list')
        self.assertEqual(response.status_code, 403)

        response = self.get('recommended-question-list')
        self.assertEqual(response.status_code, 403)
