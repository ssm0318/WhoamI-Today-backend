from django.contrib.auth import get_user_model
from test_plus.test import TestCase
from rest_framework.test import APIClient

from comment.models import Comment
from notification.models import Notification
from user_tag.models import UserTag
from feed.models import Article, Question, Response

from adoorback.utils.seed import set_seed
from adoorback.content_types import get_comment_type, get_user_tag_type

User = get_user_model()
N = 10


class UserTagTestCase(TestCase):
    def setUp(self):
        set_seed(N)

        user = self.make_user(username='user')
        friend_user_1 = self.make_user(username='friend_user_1')
        friend_user_2 = self.make_user(username='friend_user_2')
        user.friends.add(friend_user_1)
        user.friends.add(friend_user_2)
        friend_user_1.friends.add(friend_user_2)

        article = Article.objects.create(author=friend_user_1, content='test article')
        response =  Response.objects.create(author=friend_user_2, content='test response',
                                            question=Question.objects.first())

        # create comment with user_tag
        comment_1 = Comment.objects.create(author=user, target=article,
                                           content='hi @' + friend_user_2.username, is_private=False)
        comment_2 = Comment.objects.create(author=friend_user_1, target=response,
                                           content='@' + user.username, is_private=False)
        reply = Comment.objects.create(author=friend_user_2, target=comment_1,
                                       content='hey @' + user.username, is_private=False)

    def test_user_tag_create(self):
        comment_1 = Comment.objects.order_by('-created_at')[2]
        article = Article.objects.order_by('-created_at')[1]
        user_tag_1 = UserTag.objects.filter(object_id=comment_1.id, content_type=get_comment_type()).first()

        self.assertEqual(user_tag_1.tagging_user, User.objects.get(username='user'))
        self.assertEqual(user_tag_1.tagged_user, User.objects.get(username='friend_user_2'))
        self.assertEqual(user_tag_1.content_type, get_comment_type())
        self.assertEqual(user_tag_1.object_id, comment_1.id)

        reply = Comment.objects.order_by('-created_at')[0]
        user_tag = UserTag.objects.filter(object_id=reply.id, content_type=get_comment_type()).first()

        self.assertEqual(user_tag.tagging_user, User.objects.get(username='friend_user_2'))
        self.assertEqual(user_tag.tagged_user, User.objects.get(username='user'))
        self.assertEqual(user_tag.content_type, get_comment_type())
        self.assertEqual(user_tag.object_id, reply.id)

    def test_user_tag_count(self):
        self.assertEqual(UserTag.objects.count(), 3)

    def test_user_tag_str(self):
        comment_1 = Comment.objects.order_by('-created_at')[2]
        user_tag_1 = UserTag.objects.filter(object_id=comment_1.id, content_type=get_comment_type()).first()

        self.assertEqual(
            user_tag_1.__str__(),
            f'{user_tag_1.tagging_user} tagged {user_tag_1.tagged_user} in {user_tag_1.content_type} ({user_tag_1.object_id})'
            )
        self.assertEqual(user_tag_1.type, 'UserTag')

    def test_on_delete_user_cascade(self):
        # user_tag must be deleted along with tagging/tagged user
        user = User.objects.get(username='user')
        self.assertGreater(user.tagging_set.count(), 0)
        self.assertGreater(user.tagged_set.count(), 0)

        user_id = user.id
        user.delete()
        self.assertEqual(User.objects.filter(id=user_id).count(), 0)
        self.assertEqual(UserTag.objects.filter(tagging_user_id=user_id).count(), 0)
        self.assertEqual(UserTag.objects.filter(tagged_user_id=user_id).count(), 0)

    def test_on_delete_comment_cascade(self):
        # user_tag must be deleted along with target comment
        comment_1 = Comment.objects.order_by('-created_at')[2]
        comment_2 = Comment.objects.order_by('-created_at')[1]
        self.assertGreater(comment_1.comment_user_tags.count(), 0)
        self.assertGreater(comment_2.comment_user_tags.count(), 0)

        comment_model = get_comment_type()
        comment_1.delete()
        comment_2.delete()
        self.assertEqual(UserTag.objects.filter(content_type=comment_model, object_id=comment_1.id).count(), 0)
        self.assertEqual(UserTag.objects.filter(content_type=comment_model, object_id=comment_2.id).count(), 0)


class APITestCase(TestCase):
    client_class = APIClient


class UserTagAPITestCase(APITestCase):
    def setUp(self):
        set_seed(N)

        user = self.make_user(username='user')
        friend_user_1 = self.make_user(username='friend_user_1')
        friend_user_2 = self.make_user(username='friend_user_2')
        non_friend_user = self.make_user(username='non_friend_user')
        user.friends.add(friend_user_1)
        user.friends.add(friend_user_2)

        article = Article.objects.create(author=friend_user_1, content='test article')

    def test_user_tag_create(self):
        user = User.objects.get(username='user')
        friend_user_2 = User.objects.get(username='friend_user_2')
        article = Article.objects.order_by('created_at').last()

        with self.login(username=user.username, password='password'):
            self.assertEqual(UserTag.objects.count(), 0)

            data = {'target_type': 'Article', 'target_id': article.id, 'content': 'hey @' + friend_user_2.username}
            response = self.post('comment-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(UserTag.objects.count(), 1)

            user_tag_1 = UserTag.objects.last()
            self.assertEqual(user_tag_1.tagging_user, user)
            self.assertEqual(user_tag_1.tagged_user, friend_user_2)
            self.assertEqual(user_tag_1.content_type, get_comment_type())
            self.assertEqual(user_tag_1.object_id, response.data['id'])

        # user tags him/herself
        with self.login(username=user.username, password='password'):
            num_user_tags_before = UserTag.objects.count()
            data = {'target_type': 'Article', 'target_id': article.id, 'content': 'hey @' + user.username}
            response = self.post('comment-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            num_user_tags_after = UserTag.objects.count()
            self.assertEqual(num_user_tags_before, num_user_tags_after - 1)

    def test_restrictions(self):
        user = User.objects.get(username='user')
        article = Article.objects.order_by('created_at').last()

        # user tags nonexistent user
        with self.login(username=user.username, password='password'):
            num_user_tags_before = UserTag.objects.count()
            data = {'target_type': 'Article', 'target_id': article.id, 'content': 'hey @' + '유저'}
            response = self.post('comment-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            num_user_tags_after = UserTag.objects.count()
            self.assertEqual(num_user_tags_before, num_user_tags_after)  # user_tag should not have been created

        # user tags another user in an anonymous comment
        with self.login(username=user.username, password='password'):
            num_user_tags_before = UserTag.objects.count()
            data = {
                    'target_type': 'Article',
                    'target_id': article.id,
                    'content': 'hi @' + user.username,
                    'is_anonymous': True
                    }
            response = self.post('comment-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            num_user_tags_after = UserTag.objects.count()
            self.assertEqual(num_user_tags_before, num_user_tags_after)  # user_tag should not have been created

    def test_user_tag_search(self):
        user = User.objects.get(username='user')
        non_friend_user = User.objects.get(username='non_friend_user')

        # user with 2 friends
        with self.login(username=user.username, password='password'):
            response = self.get('user_tag-search', data={'query': 'user'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 2)

        with self.login(username=user.username, password='password'):
            response = self.get('user_tag-search', data={'query': '유저'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 0)

        # user with no friends
        with self.login(username=non_friend_user.username, password='password'):
            response = self.get('user_tag-search', data={'query': 'user'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 0)


class UserTagNotiAPITestCase(APITestCase):
    def setUp(self):
        set_seed(N)

        user = self.make_user(username='user')
        friend_user_1 = self.make_user(username='friend_user_1')
        friend_user_2 = self.make_user(username='friend_user_2')
        non_friend_user = self.make_user(username='non_friend_user')
        user.friends.add(friend_user_1)
        user.friends.add(friend_user_2)
        friend_user_1.friends.add(friend_user_2)

        article = Article.objects.create(author=friend_user_1, content='test article')

    def test_create_user_tag_noti(self):
        user = User.objects.get(username='user')
        friend_user_1 = User.objects.get(username='friend_user_1')
        friend_user_2 = User.objects.get(username='friend_user_2')
        non_friend_user = User.objects.get(username='non_friend_user')
        article = Article.objects.order_by('created_at').last()

        with self.login(username=user.username, password='password'):
            num_notis_before = Notification.objects.count()
            data = {'target_type': 'Article', 'target_id': article.id, 'content': 'hi @' + friend_user_2.username}
            response = self.post('comment-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            num_notis_after = Notification.objects.count()
            self.assertEqual(num_notis_before, num_notis_after - 2)
            user_tag_noti = Notification.objects.filter(
                                                        origin_id=response.data['id'],
                                                        target_type=get_user_tag_type()
                                                        ).first()
            self.assertEqual(user_tag_noti.message,
                             "user님이 댓글에서 회원님을 언급했습니다.")
            self.assertEqual(user_tag_noti.user, friend_user_2)

        # user tags another user in a comment where that user does not have permission to access
        with self.login(username=user.username, password='password'):
            data = {
                    'target_type': 'Article',
                    'target_id': article.id,
                    'content': 'can you see this @' + non_friend_user.username
                    }
            response = self.post('comment-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            user_tag_noti = Notification.objects.filter(
                                                        user_id=non_friend_user.id,
                                                        actor_id=user.id,
                                                        target_type=get_user_tag_type()
                                                        )
            self.assertEqual(user_tag_noti.count(), 0)  # user_tag noti should not have been created

        # user tags another user in a private comment (where that user does not have permission to access)
        with self.login(username=user.username, password='password'):
            data = {
                    'target_type': 'Article',
                    'target_id': article.id,
                    'content': 'can you see this @' + friend_user_2.username,
                    'is_private': True
                    }
            response = self.post('comment-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            user_tag_noti = Notification.objects.filter(
                                                        user_id=friend_user_2.id,
                                                        actor_id=user.id,
                                                        origin_id=response.data['id'],
                                                        target_type=get_user_tag_type()
                                                        )
            self.assertEqual(user_tag_noti.count(), 0)  # user_tag noti should not have been created

        # user tags author of target article in a comment
        with self.login(username=user.username, password='password'):
            data = {
                    'target_type': 'Article',
                    'target_id': article.id,
                    'content': 'I am tagging the author @' + friend_user_1.username
                    }
            response = self.post('comment-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            user_tag_noti = Notification.objects.filter(
                                                        user_id=friend_user_1.id,
                                                        actor_id=user.id,
                                                        origin_id=response.data['id'],
                                                        target_type=get_user_tag_type()
                                                        )
            self.assertEqual(user_tag_noti.count(), 0)  # user_tag noti should not have been created

        # user tags same user twice in a comment
        with self.login(username=user.username, password='password'):
            data = {
                'target_type': 'Article',
                'target_id': article.id,
                'content': '@' + friend_user_2.username + ' @' + friend_user_2.username
                }
            response = self.post('comment-create', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

            user_tag_noti = Notification.objects.filter(
                                                        user_id=friend_user_2.id,
                                                        actor_id=user.id,
                                                        origin_id=response.data['id'],
                                                        target_type=get_user_tag_type()
                                                        )
            self.assertEqual(user_tag_noti.count(), 1)  # user_tag noti should have been created only once
