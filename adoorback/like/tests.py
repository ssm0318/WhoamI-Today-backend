from django.contrib.auth import get_user_model
from test_plus.test import TestCase
from rest_framework.test import APIClient

from like.models import Like
from comment.models import Comment
from feed.models import Article
from notification.models import Notification

from adoorback.test.seed import set_seed, fill_data
from adoorback.utils.content_types import get_article_type, get_question_type, get_comment_type

User = get_user_model()
N = 10


class LikeTestCase(TestCase):
    def setUp(self):
        set_seed(N)

    def test_like_count(self):
        self.assertEqual(Like.objects.count(), N * 5)

    def test_like_str(self):
        like = Like.objects.last()
        self.assertEqual(like.__str__(), f'{like.user} likes {like.content_type} ({like.object_id})')
        self.assertEqual(like.type, 'Like')

    def test_on_delete_undelete_user_cascade(self):
        fill_data()
        user = User.objects.get(id=2)
        like_cnt = user.like_set.count()
        self.assertGreater(like_cnt, 0)

        user.delete()
        self.assertEqual(User.objects.filter(id=2).count(), 0)
        self.assertEqual(Like.objects.filter(user_id=2).count(), 0)

        # undelete
        user.undelete()
        self.assertEqual(User.objects.filter(id=2).count(), 1)
        self.assertEqual(Like.objects.filter(user_id=2).count(), like_cnt)

    # like must be deleted along with target Feed
    def test_on_delete_undelete_feed_cascade(self):
        article_model = get_article_type()
        question_model = get_question_type()
        article = Like.objects.filter(content_type=article_model).last().target
        question = Like.objects.filter(content_type=question_model).last().target
        article_id = article.id
        question_id = question.id
        article_like_cnt = Like.objects.filter(content_type=article_model, object_id=article_id).count()
        question_like_cnt = Like.objects.filter(content_type=question_model, object_id=question_id).count()
        self.assertGreater(article.article_likes.count(), 0)
        self.assertGreater(question.question_likes.count(), 0)

        article.delete()
        question.delete()
        self.assertEqual(Like.objects.filter(content_type=article_model, object_id=article_id).count(), 0)
        self.assertEqual(Like.objects.filter(content_type=question_model, object_id=question_id).count(), 0)

        # undelete
        article.undelete()
        question.undelete()
        self.assertEqual(Like.objects.filter(content_type=article_model, object_id=article_id).count(), article_like_cnt)
        self.assertEqual(Like.objects.filter(content_type=question_model, object_id=question_id).count(), question_like_cnt)

    # like must be deleted along with target Comment
    def test_delete_undelete_comment_cascade(self):
        content_type = get_comment_type()
        comment = Like.objects.filter(content_type=content_type).last().target
        object_id = comment.id
        comment_like_cnt = Like.objects.filter(content_type=content_type, object_id=object_id).count()
        self.assertGreater(comment.comment_likes.count(), 0)

        comment.delete()
        self.assertEqual(Like.objects.filter(content_type=content_type, object_id=object_id).count(), 0)

        # undelete
        comment.undelete()
        self.assertEqual(Like.objects.filter(content_type=content_type, object_id=object_id).count(), comment_like_cnt)


class APITestCase(TestCase):
    client_class = APIClient


class LikeAPITestCase(APITestCase):

    def setUp(self):
        set_seed(N)

    def test_like_create(self):
        current_user = self.make_user(username='current_user')

        with self.login(username=current_user.username, password='password'):
            data = {"target_type": "Response", "target_id": 1}
            response = self.post('like-list', data=data)
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.data['type'], "Like")

    def test_restrictions(self):
        current_user = self.make_user(username='current_user')
        spy_user = self.make_user(username='spy_user')

        with self.login(username=current_user.username, password='password'):
            data = {"target_type": "Comment", "target_id": 1}
            response = self.post('like-list', data=data)
            self.assertEqual(response.status_code, 201)

        with self.login(username=current_user.username, password='password'):
            pk = Like.objects.last().id
            response = self.delete(self.reverse('like-destroy', pk=pk))
            self.assertEqual(response.status_code, 204)

        with self.login(username=current_user.username, password='password'):
            data = {"target_type": "Comment", "target_id": 1}
            response = self.post('like-list', data=data)
            self.assertEqual(response.status_code, 201)

        with self.login(username=spy_user.username, password='password'):
            pk = Like.objects.last().id
            response = self.delete(self.reverse('like-destroy', pk=pk))
            self.assertEqual(response.status_code, 403)
 

class LikeNotiAPITestCase(APITestCase):

    def setUp(self):
        set_seed(N)

    def test_create_like_noti(self):
        current_user = self.make_user(username='current_user')

        # create like (current_user -> author of Article with id=1)
        with self.login(username=current_user.username, password='password'):
            num_notis_before = Notification.objects.count()
            data = {"target_type": "Article", "target_id": 1, "is_anonymous": True}
            response = self.post('like-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            num_notis_after = Notification.objects.count()
            self.assertEqual(num_notis_before, num_notis_after - 1)
            first_article = Article.objects.get(id=1)
            like_noti = Notification.objects.first()  # notification is order_by '-updated_at'
            self.assertIn("익명의 사용자가 회원님의 게시글을 좋아합니다", like_noti.message_ko)
            self.assertIn(first_article.content.split()[0], like_noti.message_ko)
            self.assertEqual(like_noti.user, first_article.author)
            self.assertEqual(Notification.objects.first().redirect_url, "/articles/1?anonymous=True")

        # create like (current_user -> author of Response with id=1)
        with self.login(username=current_user.username, password='password'):
            data = {"target_type": "Response", "target_id": 1, "is_anonymous": True}
            response = self.post('like-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            self.assertEqual(Notification.objects.first().redirect_url, "/responses/1?anonymous=True")

        # create like (current_user -> author of Response with id=1)
        with self.login(username=current_user.username, password='password'):
            data = {"target_type": "Question", "target_id": 1, "is_anonymous": True}
            response = self.post('like-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            self.assertEqual(Notification.objects.first().redirect_url, "/questions/1?anonymous=True")

        # create comment (current_user -> current_user): no new notification
        with self.login(username=current_user.username, password='password'):
            article = Article.objects.create(author=current_user, content="test article")
            num_notis_before = Notification.objects.count()
            data = {"target_type": "Article", "target_id": article.id}
            response = self.post('like-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            num_notis_after = Notification.objects.count()
            self.assertEqual(num_notis_before, num_notis_after)  # like noti should not have been created

        # create like (current_user -> author of Comment with id=1)
        with self.login(username=current_user.username, password='password'):
            num_notis_before = Notification.objects.count()
            data = {"target_type": "Comment", "target_id": 1, "is_anonymous": True}
            response = self.post('like-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            num_notis_after = Notification.objects.count()
            self.assertEqual(num_notis_before, num_notis_after - 1)
            first_comment = Comment.objects.get(id=1)
            like_noti = Notification.objects.first()  # notification is order_by '-updated_at'
            self.assertIn("익명의 사용자가 회원님의 댓글을 좋아합니다", like_noti.message_ko)
            self.assertIn(first_comment.content.split()[0], like_noti.message_ko)
            self.assertEqual(like_noti.user, first_comment.author)

        # create like (current_user -> current_user): no new notification
        with self.login(username=current_user.username, password='password'):
            comment = Comment.objects.create(author=current_user, content="test comment",
                                             target=Article.objects.last())
            num_notis_before = Notification.objects.count()
            data = {"target_type": "Comment", "target_id": comment.id, "content": "test_reply"}
            response = self.post('like-list', data=data, extra={'format': 'json'}) 
            self.assertEqual(response.status_code, 201)

            num_notis_after = Notification.objects.count()
            self.assertEqual(num_notis_before, num_notis_after)  # reply noti should not have been created

        # friend user noti should display username in noti message
        friend_user = self.make_user(username='friend_user')
        current_user.friends.add(friend_user)
        with self.login(username=friend_user.username, password='password'):
            last_comment =  Comment.objects.last()
            data = {"target_type": "Comment", "target_id": last_comment.id}
            response = self.post('like-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)
            like_noti = Notification.objects.first()
            self.assertIn("friend_user님이 회원님의 댓글을 좋아합니다", like_noti.message_ko)
            self.assertIn(last_comment.content.split()[0], like_noti.message_ko)
