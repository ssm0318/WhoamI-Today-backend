from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from account.models import Connection, FriendRequest, Subscription
from account.serializers import FriendListSerializer, UserProfileSerializer
from check_in.models import CheckIn, Song
from notification.models import Notification

User = get_user_model()


def get_check_in_ct():
    return ContentType.objects.get_for_model(CheckIn)


class CheckInSubscriptionDefaultTests(TestCase):
    """Test that default subscriptions are created on friendship creation."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            username='user_a', email='a@test.com', password='pw',
            current_ver='version_w',
        )
        self.user_b = User.objects.create_user(
            username='user_b', email='b@test.com', password='pw',
            current_ver='version_w',
        )

    def _accept_friend_request(self, requester, requestee,
                               requester_choice='friend', requestee_choice='friend'):
        fr = FriendRequest.objects.create(
            requester=requester, requestee=requestee,
            requester_choice=requester_choice, requestee_choice=requestee_choice,
        )
        fr.accepted = True
        fr.save()
        return fr

    def test_close_friend_creates_subscription(self):
        """When both set close_friend, both get subscriptions."""
        self._accept_friend_request(
            self.user_a, self.user_b,
            requester_choice='close_friend', requestee_choice='close_friend',
        )
        ct = get_check_in_ct()
        self.assertTrue(Subscription.objects.filter(
            subscriber=self.user_a, subscribed_to=self.user_b, content_type=ct
        ).exists())
        self.assertTrue(Subscription.objects.filter(
            subscriber=self.user_b, subscribed_to=self.user_a, content_type=ct
        ).exists())

    def test_one_close_friend_creates_one_subscription(self):
        """Only the user who set close_friend gets a subscription."""
        self._accept_friend_request(
            self.user_a, self.user_b,
            requester_choice='close_friend', requestee_choice='friend',
        )
        ct = get_check_in_ct()
        # requester set close_friend → requester subscribes to requestee
        self.assertTrue(Subscription.objects.filter(
            subscriber=self.user_a, subscribed_to=self.user_b, content_type=ct
        ).exists())
        # requestee set friend → no subscription
        self.assertFalse(Subscription.objects.filter(
            subscriber=self.user_b, subscribed_to=self.user_a, content_type=ct
        ).exists())

    def test_regular_friend_no_subscription(self):
        """No subscriptions when both set friend."""
        self._accept_friend_request(
            self.user_a, self.user_b,
            requester_choice='friend', requestee_choice='friend',
        )
        ct = get_check_in_ct()
        self.assertEqual(Subscription.objects.filter(content_type=ct).count(), 0)

    def test_version_q_no_subscription(self):
        """version_q users don't get auto-subscriptions."""
        self.user_a.current_ver = 'version_q'
        self.user_a.save()
        self.user_b.current_ver = 'version_q'
        self.user_b.save()

        self._accept_friend_request(
            self.user_a, self.user_b,
            requester_choice='close_friend', requestee_choice='close_friend',
        )
        ct = get_check_in_ct()
        self.assertEqual(Subscription.objects.filter(content_type=ct).count(), 0)


class CheckInSubscriptionCleanupTests(TestCase):
    """Test that subscriptions are cleaned up when Connection is deleted."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            username='user_a', email='a@test.com', password='pw',
            current_ver='version_w',
        )
        self.user_b = User.objects.create_user(
            username='user_b', email='b@test.com', password='pw',
            current_ver='version_w',
        )
        self.conn = Connection.objects.create(
            user1=self.user_a, user2=self.user_b,
            user1_choice='close_friend', user2_choice='close_friend',
        )
        ct = get_check_in_ct()
        Subscription.objects.create(subscriber=self.user_a, subscribed_to=self.user_b, content_type=ct)
        Subscription.objects.create(subscriber=self.user_b, subscribed_to=self.user_a, content_type=ct)

    def test_unfriend_removes_subscriptions(self):
        ct = get_check_in_ct()
        self.assertEqual(Subscription.objects.filter(content_type=ct).count(), 2)

        self.conn.delete()

        self.assertEqual(Subscription.objects.filter(content_type=ct).count(), 0)


class CheckInSubscribeToggleAPITests(TestCase):
    """Test the subscribe/unsubscribe toggle endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='me', email='me@test.com', password='pw',
            current_ver='version_w',
        )
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='pw',
            current_ver='version_w',
        )
        Connection.objects.create(
            user1=self.user, user2=self.friend,
            user1_choice='friend', user2_choice='friend',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.subscribe_url = reverse('check-in-subscribe-add')
        self.unsubscribe_url = reverse('check-in-subscribe-destroy', kwargs={'pk': self.friend.id})

    def test_subscribe_success(self):
        resp = self.client.post(self.subscribe_url, {'friend_id': self.friend.id})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Subscription.objects.filter(
            subscriber=self.user, subscribed_to=self.friend, content_type=get_check_in_ct()
        ).exists())

    def test_subscribe_duplicate_returns_400(self):
        Subscription.objects.create(
            subscriber=self.user, subscribed_to=self.friend, content_type=get_check_in_ct()
        )
        resp = self.client.post(self.subscribe_url, {'friend_id': self.friend.id})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_subscribe_non_friend_returns_400(self):
        stranger = User.objects.create_user(
            username='stranger', email='s@test.com', password='pw',
            current_ver='version_w',
        )
        resp = self.client.post(self.subscribe_url, {'friend_id': stranger.id})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unsubscribe_success(self):
        Subscription.objects.create(
            subscriber=self.user, subscribed_to=self.friend, content_type=get_check_in_ct()
        )
        resp = self.client.delete(self.unsubscribe_url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Subscription.objects.filter(
            subscriber=self.user, subscribed_to=self.friend, content_type=get_check_in_ct()
        ).exists())

    def test_version_q_user_gets_403(self):
        self.user.current_ver = 'version_q'
        self.user.save()
        resp = self.client.post(self.subscribe_url, {'friend_id': self.friend.id})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class CheckInNotificationTests(TestCase):
    """Test notification creation on check-in updates."""

    def setUp(self):
        self.author = User.objects.create_user(
            username='author', email='author@test.com', password='pw',
            current_ver='version_w',
        )
        self.subscriber = User.objects.create_user(
            username='subscriber', email='sub@test.com', password='pw',
            current_ver='version_w',
        )
        Connection.objects.create(
            user1=self.author, user2=self.subscriber,
            user1_choice='close_friend', user2_choice='close_friend',
        )
        Subscription.objects.create(
            subscriber=self.subscriber, subscribed_to=self.author,
            content_type=get_check_in_ct(),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.author)
        self.checkin_url = reverse('current-check-in')

    def test_new_checkin_sends_notification(self):
        """Creating a new check-in with content sends a notification."""
        resp = self.client.post(self.checkin_url, {
            'thought': 'hello world', 'visibility': ['friends'],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        noti = Notification.objects.filter(user=self.subscriber)
        self.assertEqual(noti.count(), 1)
        self.assertIn('체크인', noti.first().message_ko)

    def test_empty_checkin_no_notification(self):
        """Creating a check-in with no content sends no notification."""
        resp = self.client.post(self.checkin_url, {
            'thought': '', 'visibility': ['friends'],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Notification.objects.filter(user=self.subscriber).count(), 0)

    def test_update_checkin_sends_notification(self):
        """Updating existing check-in content triggers notification."""
        # Create initial check-in
        CheckIn.objects.create(user=self.author, is_active=True, thought='old',
                               visibility=['friends'])

        # Update via API
        resp = self.client.post(self.checkin_url, {
            'thought': 'new thought', 'visibility': ['friends'],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Notification.objects.filter(user=self.subscriber).count(), 1)

    def test_no_change_no_notification(self):
        """Updating with same content doesn't trigger notification."""
        CheckIn.objects.create(user=self.author, is_active=True, thought='same',
                               visibility=['friends'])

        resp = self.client.post(self.checkin_url, {
            'thought': 'same', 'visibility': ['friends'],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Notification.objects.filter(user=self.subscriber).count(), 0)

    def test_batching_within_5_minutes(self):
        """Multiple updates within 5 min produce only 1 notification."""
        self.client.post(self.checkin_url, {
            'thought': 'first', 'visibility': ['friends'],
        }, format='json')
        self.assertEqual(Notification.objects.filter(user=self.subscriber).count(), 1)

        self.client.post(self.checkin_url, {
            'thought': 'second', 'visibility': ['friends'],
        }, format='json')
        # Still only 1 notification (updated, not duplicated)
        self.assertEqual(Notification.objects.filter(user=self.subscriber).count(), 1)

        noti = Notification.objects.filter(user=self.subscriber).first()
        self.assertIn('체크인', noti.message_ko)

    def test_song_change_sends_notification(self):
        """Creating a song when there's an active check-in sends notification."""
        CheckIn.objects.create(user=self.author, is_active=True, thought='hi')

        song_url = reverse('current-song')
        resp = self.client.post(song_url, {'track_id': 'spotify:123'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Notification.objects.filter(user=self.subscriber).count(), 1)

    def test_song_without_checkin_no_notification(self):
        """Creating a song without active check-in sends no notification."""
        song_url = reverse('current-song')
        resp = self.client.post(song_url, {'track_id': 'spotify:123'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Notification.objects.filter(user=self.subscriber).count(), 0)

    def test_version_q_author_no_notification(self):
        """version_q author's check-in doesn't trigger notifications."""
        self.author.current_ver = 'version_q'
        self.author.save()

        self.client.post(self.checkin_url, {
            'thought': 'hello', 'visibility': ['friends'],
        }, format='json')
        self.assertEqual(Notification.objects.filter(user=self.subscriber).count(), 0)


class CheckInSubscriptionSerializerTests(TestCase):
    """Test that is_check_in_subscribed appears correctly in serializers."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='me', email='me@test.com', password='pw',
            current_ver='version_w',
        )
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='pw',
            current_ver='version_w',
        )
        Connection.objects.create(
            user1=self.user, user2=self.friend,
            user1_choice='close_friend', user2_choice='friend',
        )
        self.factory = APIRequestFactory()

    def test_profile_subscribed_true(self):
        Subscription.objects.create(
            subscriber=self.user, subscribed_to=self.friend,
            content_type=get_check_in_ct(),
        )
        request = self.factory.get('/')
        request.user = self.user
        serializer = UserProfileSerializer(self.friend, context={'request': request})
        self.assertTrue(serializer.data['is_check_in_subscribed'])

    def test_profile_not_subscribed_false(self):
        request = self.factory.get('/')
        request.user = self.user
        serializer = UserProfileSerializer(self.friend, context={'request': request})
        self.assertFalse(serializer.data['is_check_in_subscribed'])

    def test_friend_list_uses_batch_context(self):
        Subscription.objects.create(
            subscriber=self.user, subscribed_to=self.friend,
            content_type=get_check_in_ct(),
        )
        request = self.factory.get('/')
        request.user = self.user
        context = {
            'request': request,
            'check_in_subscription_ids': {self.friend.id},
            'favorite_ids': set(),
            'hidden_ids': set(),
            'connection_by_friend_id': {},
            'visible_check_in_by_user_id': {},
            'active_song_by_user_id': {},
            'unread_note_count_by_author': {},
            'unread_response_count_by_author': {},
            'unread_chat_count_by_friend_id': {},
            'visible_notes_by_author': {},
            'visible_resps_by_author': {},
            'pokes_by_receiver': {},
        }
        serializer = FriendListSerializer(self.friend, context=context)
        self.assertTrue(serializer.data['is_check_in_subscribed'])

    def test_version_q_always_false(self):
        self.user.current_ver = 'version_q'
        self.user.save()
        Subscription.objects.create(
            subscriber=self.user, subscribed_to=self.friend,
            content_type=get_check_in_ct(),
        )
        request = self.factory.get('/')
        request.user = self.user
        serializer = UserProfileSerializer(self.friend, context={'request': request})
        self.assertFalse(serializer.data['is_check_in_subscribed'])
