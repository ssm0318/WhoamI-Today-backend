from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError
from django.test import Client
from rest_framework.test import APIClient
from rest_framework.utils import json
from test_plus.test import TestCase

from account.models import FriendRequest
from adoorback.test.seed import set_seed
from notification.models import Notification

User = get_user_model()
N = 10


class UserTestCase(TestCase):
    def setUp(self):
        set_seed(N)

    def test_user_count(self):
        self.assertEqual(User.objects.count(), 3)

    def test_str(self):
        user = User.objects.last()
        self.assertEqual(user.type, 'User')


class UserFriendshipCase(TestCase):
    def setUp(self):
        set_seed(N)

    def test_on_friend_request_create_friendship(self):
        user = User.objects.first()
        self.assertEqual(user.friends.count(), 1)

    def test_on_delete_undelete_user_cascade(self):
        user = User.objects.first()
        user_id = user.id
        friend = user.friends.first()
        friends_cnt = friend.friends.count()

        user.delete()
        self.assertEqual(User.objects.filter(id=user_id).count(), 0)
        self.assertEqual(friend.friends.count(), friends_cnt - 1)

        # undelete
        user.undelete()
        self.assertEqual(User.objects.filter(id=user_id).count(), 1)
        self.assertEqual(friend.friends.count(), friends_cnt)


class FriendRequestTestCase(TestCase):
    def setUp(self):
        set_seed(N)

    def test_friend_request_count(self):
        self.assertEqual(FriendRequest.objects.count(), 2)

    def test_friend_request_str(self):
        friendrequest = FriendRequest.objects.first()
        self.assertEqual(friendrequest.type, 'FriendRequest')
        self.assertEqual(friendrequest.__str__(),
                         f'{friendrequest.requester} sent to {friendrequest.requestee} ({friendrequest.accepted})')

    def test_on_delete_undelete_requester_cascade(self):
        user = FriendRequest.objects.first().requester
        sent_friend_requests_cnt = user.sent_friend_requests.all().count()
        self.assertEqual(sent_friend_requests_cnt, 2)

        user.delete()
        self.assertEqual(User.objects.filter(id=user.id).count(), 0)
        self.assertEqual(FriendRequest.objects.filter(requester_id=user.id).count(), 0)
        self.assertEqual(FriendRequest.objects.filter(requestee_id=user.id).count(), 0)

        # undelete
        user.undelete()
        self.assertEqual(User.objects.filter(id=user.id).count(), 1)
        self.assertEqual(FriendRequest.objects.filter(requester_id=user.id).count(), sent_friend_requests_cnt)

    def test_on_delete_undelete_requestee_cascade(self):
        user = FriendRequest.objects.first().requestee
        received_friend_requests_cnt = user.received_friend_requests.all().count()
        self.assertEqual(received_friend_requests_cnt, 1)

        user.delete()
        self.assertEqual(User.objects.filter(id=user.id).count(), 0)
        self.assertEqual(FriendRequest.objects.filter(requester_id=user.id).count(), 0)
        self.assertEqual(FriendRequest.objects.filter(requestee_id=user.id).count(), 0)

        # undelete
        user.undelete()
        self.assertEqual(User.objects.filter(id=user.id).count(), 1)
        self.assertEqual(FriendRequest.objects.filter(requestee_id=user.id).count(), received_friend_requests_cnt)

    def test_on_delete_undelete_responder_cascade(self):
        user = FriendRequest.objects.first().requestee
        received_friend_requests_cnt = user.received_friend_requests.all().count()
        self.assertGreater(received_friend_requests_cnt, 0)

        user.delete()
        self.assertEqual(User.objects.filter(id=user.id).count(), 0)
        self.assertEqual(FriendRequest.objects.filter(requester_id=user.id).count(), 0)
        self.assertEqual(FriendRequest.objects.filter(requestee_id=user.id).count(), 0)

        # undelete
        user.undelete()
        self.assertEqual(User.objects.filter(id=user.id).count(), 1)
        self.assertEqual(FriendRequest.objects.filter(requestee_id=user.id).count(), received_friend_requests_cnt)


class APITestCase(TestCase):
    client_class = APIClient


class UserAPITestCase(APITestCase):
    def setUp(self):
        set_seed(N)

    def test_search(self):
        current_user = self.make_user(username='current_user')

        with self.login(username=current_user.username, password='password'):
            response = self.get('user-search', data={'query': 'current_user'})
            self.assertEqual(response.status_code, 200)
            self.assertGreaterEqual(response.data['count'], 1)
            # `are_friends` for self should return null
            self.assertEqual(response.data['results'][0]['are_friends'], None)

        with self.login(username=current_user.username, password='password'):
            response = self.get('user-search', data={'query': '어두워'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 0)

        with self.login(username=current_user.username, password='password'):
            response = self.get('user-search')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 0)  # empty query should return empty search result

    def test_friend_list(self):
        current_user = self.make_user(username='current_user')

        with self.login(username=current_user.username, password='password'):
            response = self.get('current-user-friends')
            self.assertEqual(response.status_code, 200)

    def test_user_friend_detail(self):
        current_user = self.make_user(username='current_user')
        friend_user = self.make_user(username='friend_user')

        # User model property/class method test
        current_user.friends.add(friend_user)
        self.assertEqual(current_user.friend_ids, [friend_user.id])
        self.assertTrue(User.are_friends(current_user, friend_user))

        with self.login(username=current_user.username, password='password'):
            response = self.delete(
                self.reverse('user-friend-destroy', pk=friend_user.id))
            self.assertEqual(response.status_code, 204)


class AuthAPITestCase(APITestCase):
    def setUp(self):
        set_seed(N)

    def test_csrf(self):
        self.make_user(username='username')

        client = Client(enforce_csrf_checks=True)

        login_data = {"username": "username", "password": "password"}

        response = client.post('/api/user/token/',
                               json.dumps(login_data),
                               content_type='application/json')
        self.assertEqual(response.status_code, 200)

        csrftoken = response.cookies['csrftoken'].value
        signup_data2 = {"username": "test_username2",
                        "password": "test_password", "email": "test2@email.com"}
        response = client.post('/api/user/signup/',
                               json.dumps(signup_data2),
                               HTTP_X_CSRFTOKEN=csrftoken,
                               content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_signup(self):
        client = Client()

        # GET request
        response = client.get('/api/user/signup/')
        self.assertEqual(response.status_code, 405)  # Request not allowed

        # empty json
        response = client.post('/api/user/signup/', {},
                               content_type='application/json')
        self.assertEqual(response.status_code, 400)

        # normal signup
        signup_data = {
            'username': 'test_username',
            'password': 'test_password',
            'email': 'test@email.com',
        }
        response = client.post('/api/user/signup/',
                               signup_data, content_type='application/json')
        self.assertEqual(response.status_code, 201)

        # inactive user
        response = client.post('/api/user/signup/',
                               signup_data, content_type='application/json')
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.data['detail'].code, 'user_is_inactive')

        # existing username
        test_user = User.objects.get(username='test_username')
        test_user.is_active = True
        test_user.save()
        signup_data = {
            'username': 'test_username',
            'password': 'test_existing_username',
            'email': 'test_existing_username@email.com',
        }
        response = client.post('/api/user/signup/',
                               signup_data, content_type='application/json')
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.data['detail'].code, 'username_exists')

        # existing email
        signup_data = {
            "username": "test_existing_email",
            "password": "test_existing_email",
            "email": "test@email.com"
        }
        response = client.post(
            '/api/user/signup/', signup_data, content_type='application/json')
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.data['detail'].code, 'email_exists')

        # invalid email
        signup_data = {
            "username": "test_invalid_email",
            "password": "test_invalid_email",
            "email": "test_invalid_email@"
        }
        response = client.post(
            '/api/user/signup/', signup_data, content_type='application/json')
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.data['detail'].code, 'email_invalid')

    def test_login(self):
        # GET request
        response = self.client.get('/api/user/token/')
        self.assertEqual(response.status_code, 405)  # Request not allowed

        # empty json
        response = self.client.post('/api/token/', {},
                               content_type='application/json')
        self.assertEqual(response.status_code, 404)

        # normal login
        User.objects.create_user(
            username="test_username", email="test@email.com", password="test_password")
        login_data = {"username": "test_username", "password": "test_password"}
        response = self.client.post(
            '/api/user/token/', json.dumps(login_data), content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # no username
        login_data = {'username': 'test_no_username', 'password': 'test_no_username'}
        response = self.client.post(
            '/api/user/token/', json.dumps(login_data), content_type='application/json')
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.data['detail'].code, 'username_does_not_exist')

        # wrong password
        login_data = {'username': 'test_username', 'password': 'test_wrong_password'}
        response = self.client.post(
            '/api/user/token/', json.dumps(login_data), content_type='application/json')
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.data['detail'].code, 'wrong_password')

        # inactive user
        test_user = User.objects.get(username='test_username')
        test_user.is_active = False
        test_user.save()
        login_data = {'username': 'test_username', 'password': 'test_password'}
        response = self.client.post(
            '/api/user/token/', json.dumps(login_data), content_type='application/json')
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.data['detail'].code, 'user_is_inactive')

    def test_user_list(self):
        current_user = self.make_user(username='current_user')
        admin_user = self.make_user(username='admin_user')
        admin_user.is_superuser = True
        admin_user.save()

        with self.login(username=current_user.username, password='password'):
            response = self.get('user-list')
            self.assertEqual(response.data['count'], 1)

        with self.login(username=admin_user.username, password='password'):
            response = self.get('user-list')

            n = User.objects.count()
            self.assertEqual(response.data['count'], n)

    def test_current_user(self):
        self.make_user(username="test_user", password="test_pw")
        with self.login(username="test_user", password="test_pw"):
            response = self.get('current-user')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['username'], "test_user")

            data = {"question_history": '1, 2, 3'}
            response = self.patch('current-user', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)

            data = {"question_history": '1, 2, 3'}
            response = self.post('current-user', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 405)

    def test_current_user_update(self):
        self.make_user(username="test_user", password="test_pw")
        with self.login(username="test_user", password="test_pw"):
            data = {"question_history": True}
            response = self.patch('current-user', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 400)


class FriendRequestAPITestCase(APITestCase):
    def setUp(self):
        set_seed(N)

    def test_friend_request_list(self):
        current_user = self.make_user(username='current_user')
        friend_user = self.make_user(username='friend_user')

        # no friend friend request initially
        with self.login(username=friend_user.username, password='password'):
            response = self.get('user-friend-request-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 0)

        # make new friend request (friend_user -> current_user)
        with self.login(username=friend_user.username, password='password'):
            response = self.post('user-friend-request-list',
                                 data={"requester_id": friend_user.id,
                                       "requestee_id": current_user.id}, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(FriendRequest.objects.last().accepted, None)

        # make new friend request (friend_user -> current_user): unique constraint
        with self.login(username=friend_user.username, password='password'):
            with self.assertRaises(IntegrityError):
                response = self.post('user-friend-request-list',
                                    data={"requester_id": friend_user.id,
                                        "requestee_id": current_user.id}, extra={'format': 'json'})

        # current user has one friend request
        with self.login(username=current_user.username, password='password'):
            response = self.get('user-friend-request-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 1)  #

    def test_friend_request_detail(self):
        current_user = self.make_user(username='current_user')
        friend_user_1 = self.make_user(username='friend_user_1')
        friend_user_2 = self.make_user(username='friend_user_2')

        # POST FriendRequest (friend_user_2 -> friend_user_1)
        with self.login(username=friend_user_2.username, password='password'):
            data = {"requester_id": friend_user_2.id, "requestee_id": friend_user_1.id}
            response = self.post('user-friend-request-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        # POST FriendRequest (friend_user_2 making request for current_user -> friend_user_1): not allowed
        with self.login(username=friend_user_2.username, password='password'):
            data = {"requester_id": current_user.id, "requestee_id": friend_user_1.id}
            response = self.post('user-friend-request-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 403)

        # POST FriendRequest (current_user -> current_user): not allowed
        with self.login(username=current_user.username, password='password'):
            data = {"requester_id": current_user.id, "requestee_id": current_user.id}
            response = self.post('user-friend-request-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 400)

        # PATCH (reject) FriendRequest (friend_user_1 -> friend_user_2)
        with self.login(username=friend_user_1.username, password='password'):
            data = {"accepted": False}
            response = self.patch(self.reverse(
                'user-friend-request-update', pk=friend_user_2.id), data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)

        # DESTROY FriendRequest (friend_user_2 -> friend_user_1)
        with self.login(username=friend_user_2.username, password='password'):
            response = self.delete(self.reverse(
                'user-friend-request-destroy', pk=friend_user_1.id))
            self.assertEqual(response.status_code, 204)

        # POST FriendRequest (current_user -> friend_user_1)
        with self.login(username=current_user.username, password='password'):
            data = {"requester_id": current_user.id, "requestee_id": friend_user_1.id}
            response = self.post('user-friend-request-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(FriendRequest.objects.first().requester, current_user)  # check order_by
            self.assertEqual(FriendRequest.objects.first().requestee, friend_user_1)

        # PATCH (accept) FriendRequest (friend_user_1 -> current_user)
        with self.login(username=friend_user_1.username, password='password'):
            data = {"accepted": True}
            response = self.patch(self.reverse(
                'user-friend-request-update', pk=current_user.id), data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)

            # PATCH (accept) FriendRequest (friend_user_1 -> current_user): wrong (repeated) body
            data = {"accepted": True}
            response = self.patch(self.reverse(
                'user-friend-request-update', pk=current_user.id), data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 400)

        # PATCH FriendRequest (friend_user_1 -> current_user): wrong body
        with self.login(username=friend_user_1.username, password='password'):
            data = {"responded": True}
            response = self.patch(self.reverse(
                'user-friend-request-update', pk=current_user.id), data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 400)

        # GET (accept) FriendRequest (friend_user_1 -> current_user): not allowed
        with self.login(username=friend_user_1.username, password='password'):
            response = self.get(self.reverse(
                'user-friend-request-update', pk=current_user.id))
            self.assertEqual(response.status_code, 405)


class UserNotisAPITestCase(APITestCase):
    def setUp(self):
        set_seed(N)

    def test_signup_notis(self):
        signup_data = {
            'username': 'test_username',
            'password': 'test_password',
            'email': 'test@email.com',
        }

        num_admin_notis_before = Notification.objects.admin_only().count()
        response = self.post('user-signup', data=signup_data, extra={'format': 'json'})
        self.assertEqual(response.status_code, 201)

        self.assertEqual(Notification.objects.first().message_ko,
                         'test_username님, 반갑습니다! :) 먼저 익명피드를 둘러볼까요?')

        test_user = User.objects.get(username='test_username')
        test_user.is_active = True
        test_user.save()

        data = {"my_bad": '1, 2, 3'}
        with self.login(username='test_username', password='test_password'):
            response = self.patch('current-user', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)

            self.assertNotEqual(Notification.objects.first().message_ko,
                                'test_username님, 질문 선택을 완료해주셨네요 :) 그럼 오늘의 질문들을 둘러보러 가볼까요?')

        data = {"question_history": '1, 2, 3'}
        with self.login(username='test_username', password='test_password'):
            response = self.patch('current-user', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)

            self.assertEqual(Notification.objects.first().message_ko,
                             'test_username님, 질문 선택을 완료해주셨네요 :) 그럼 오늘의 질문들을 둘러보러 가볼까요?')

        num_admin_notis_after = Notification.objects.admin_only().count()
        self.assertEqual(num_admin_notis_before, num_admin_notis_after - 2)


class FriendshipNotisAPITestCase(APITestCase):
    def test_friend_request_noti(self):
        current_user = self.make_user(username='current_user')
        friend_user = self.make_user(username='friend_user')

        # POST FriendRequest (friend_user -> current_user)
        with self.login(username=friend_user.username, password='password'):
            data = {"requester_id": friend_user.id, "requestee_id": current_user.id}
            response = self.post('user-friend-request-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(FriendRequest.objects.last().accepted, None)  # accepted == null initially

            # notification should be auto-generated via @post_save receiver
            notification = Notification.objects.last()
            self.assertEqual(notification.actor_id, friend_user.id)
            self.assertEqual(notification.user_id, current_user.id)
            self.assertEqual(notification.is_read, False)
            self.assertEqual(notification.is_visible, True)
            self.assertEqual(notification.redirect_url, f'/users/{friend_user.username}')

        # PATCH (reject) FriendRequest (current_user -> friend_user)
        with self.login(username=current_user.username, password='password'):
            data = {"accepted": False}
            response = self.patch(self.reverse(
                'user-friend-request-update', pk=friend_user.id), data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(FriendRequest.objects.last().accepted, False)

            # notification should be *updated* via @post_save receiver
            notification = Notification.objects.last()
            self.assertEqual(notification.actor_id, friend_user.id)
            self.assertEqual(notification.user_id, current_user.id)
            self.assertEqual(notification.is_read, True)
            self.assertEqual(notification.is_visible, False)

        # DESTROY FriendRequest (friend_user -> current_user)
        with self.login(username=friend_user.username, password='password'):
            num_notis = Notification.objects.count()
            response = self.delete(self.reverse(
                'user-friend-request-destroy', pk=current_user.id))
            self.assertEqual(response.status_code, 204)
            self.assertEqual(Notification.objects.count(), num_notis - 1)  # noti destroyed as well

    def test_friendship_noti(self):
        current_user = self.make_user(username='current_user')
        friend_user = self.make_user(username='friend_user')

        # POST FriendRequest (friend_user -> current_user)
        with self.login(username=friend_user.username, password='password'):
            num_notis = Notification.objects.count()
            data = {"requester_id": friend_user.id, "requestee_id": current_user.id}
            response = self.post('user-friend-request-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(Notification.objects.count(), num_notis + 1)  # noti created

        # PATCH (accept) FriendRequest (current_user -> friend_user)
        with self.login(username=current_user.username, password='password'):
            num_notis = Notification.objects.count()
            data = {"accepted": True}
            response = self.patch(self.reverse(
                'user-friend-request-update', pk=friend_user.id), data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 200)

            self.assertEqual(Notification.objects.count(), num_notis + 2)  # two friendship notis created
            self.assertEqual(FriendRequest.objects.last().accepted, True)  # friend request model modified

            # friend request noti modified
            last_noti_id = Notification.objects.first().id
            friend_request_noti = Notification.objects.get(id=last_noti_id - 2)
            self.assertEqual(friend_request_noti.is_visible, False)  # should no longer be visible
            self.assertEqual(friend_request_noti.is_read, True)

            # friends have one newly created noti each
            current_user_friend_notis = current_user.friendship_targetted_notis.filter(user=friend_user,
                                                                                       actor=current_user)
            friend_user_friend_notis = friend_user.friendship_targetted_notis.filter(user=current_user,
                                                                                     actor=friend_user)
            self.assertEqual(current_user_friend_notis.count(), 1)
            self.assertEqual(friend_user_friend_notis.count(), 1)

        # DELETE Friendship (current_user -> friend_user)
        with self.login(username=current_user.username, password='password'):
            num_notis = Notification.objects.count()
            num_friends_current_user = User.objects.get(id=current_user.id).friends.count()
            num_friends_friend_user = User.objects.get(id=friend_user.id).friends.count()
            response = self.delete(self.reverse('user-friend-destroy', pk=friend_user.id))

            # notis should also be delete via @m2m_changed method
            self.assertEqual(response.status_code, 204)
            # three friendship notis deleted; one friend request noti, two friendship notis
            self.assertEqual(Notification.objects.count(), num_notis - 3)
            self.assertEqual(User.objects.get(id=current_user.id).friends.count(), num_friends_current_user - 1)
            self.assertEqual(User.objects.get(id=friend_user.id).friends.count(), num_friends_friend_user - 1)


class ExceptionHandlerAPITestCase(APITestCase):
    def setUp(self):
        set_seed(N)

    def test_exception_raised(self):
        response = self.get('signup-questions')
        self.assertEqual(response.status_code, 401)

        response = self.get('current_user_friends')
        self.assertEqual(response.status_code, 404)

        response = self.get(self.reverse('user-detail', username=User.objects.get(id=1).username))
        self.assertEqual(response.status_code, 401)

        response = self.delete(self.reverse('user-friend-destroy', pk=1))
        self.assertEqual(response.status_code, 401)

        response = self.delete(self.reverse('user-friend-request-destroy', pk=1))
        self.assertEqual(response.status_code, 401)

        response = self.get('user-search', data={'query': 'haha'})
        self.assertEqual(response.status_code, 401)
