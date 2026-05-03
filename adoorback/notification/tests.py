"""
Tests for notify_firebase – Firebase push notification message construction.

These tests use unittest.mock so no real Firebase credentials are needed.
Run with:
    python manage.py test notification.tests
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from firebase_admin import messaging


def _make_qs(devices):
    """Return a MagicMock that behaves like a Django QuerySet for the subset of
    methods that notify_firebase actually uses (.count(), iteration)."""
    qs = MagicMock()
    qs.count.return_value = len(devices)
    qs.__iter__ = MagicMock(return_value=iter(devices))
    return qs

User = get_user_model()


def _make_device(device_id, device_type, language='en'):
    device = MagicMock()
    device.id = device_id
    device.type = device_type
    device.language = language
    device.send_message = MagicMock(return_value={'name': 'projects/test/messages/fake'})
    return device


def _make_notification(user, message_en='Hello!', message_ko='안녕!', redirect_url='/home'):
    noti = MagicMock()
    noti.id = 1
    noti.user = user
    noti.user_id = user.id
    noti.message_en = message_en
    noti.message_ko = message_ko
    noti.redirect_url = redirect_url

    # target_type / origin_type with a .model attribute
    target_type = MagicMock()
    target_type.model = 'like'
    noti.target_type = target_type

    origin_type = MagicMock()
    origin_type.model = 'note'
    noti.origin_type = origin_type

    noti.origin_id = 42
    return noti


def _assert_ios_uses_collapse_tag(test_case, sent_message, expected_tag):
    test_case.assertEqual(sent_message.data['tag'], expected_tag)
    test_case.assertEqual(sent_message.apns.headers['apns-collapse-id'], expected_tag)
    test_case.assertEqual(sent_message.apns.payload.aps.thread_id, expected_tag)


def _make_message_notification(user, chat_room_id=123):
    noti = _make_notification(user, message_en='adoor_2 sent you 3 messages!')

    target_type = MagicMock()
    target_type.model = 'message'
    noti.target_type = target_type

    target = MagicMock()
    target.chat_room_id = chat_room_id
    noti.target = target

    return noti


class NotifyFirebaseIosAlertTest(TestCase):
    """
    Ensures that the iOS APNS message is built with an encoder-safe alert.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='pw'
        )

    @patch('notification.models.CustomFCMDevice.objects.filter')
    def test_ios_alert_is_encoder_safe_string(self, mock_filter):
        """The Aps.alert field must pass Firebase Admin's encoder."""
        ios_device = _make_device(device_id=10, device_type='ios', language='en')
        mock_filter.return_value = _make_qs([ios_device])

        noti = _make_notification(self.user, message_en='You got a like!', message_ko='좋아요 받았어요!')

        from notification.models import notify_firebase
        notify_firebase(noti)

        # send_message must have been called exactly once
        ios_device.send_message.assert_called_once()
        sent_message = ios_device.send_message.call_args[0][0]

        aps = sent_message.apns.payload.aps
        self.assertEqual(aps.alert, 'You got a like!')
        messaging._MessagingService.encode_message(sent_message)
        _assert_ios_uses_collapse_tag(self, sent_message, 'like_note_42')

    @patch('notification.models.CustomFCMDevice.objects.filter')
    def test_ios_alert_uses_korean_body_for_ko_device(self, mock_filter):
        """Korean-language devices must receive the Korean body text."""
        ios_device = _make_device(device_id=11, device_type='ios', language='ko')
        mock_filter.return_value = _make_qs([ios_device])

        noti = _make_notification(self.user, message_en='You got a like!', message_ko='좋아요 받았어요!')

        from notification.models import notify_firebase
        notify_firebase(noti)

        sent_message = ios_device.send_message.call_args[0][0]
        aps = sent_message.apns.payload.aps
        self.assertEqual(aps.alert, '좋아요 받았어요!')
        messaging._MessagingService.encode_message(sent_message)

    @patch('notification.models.CustomFCMDevice.objects.filter')
    def test_ios_chat_message_uses_room_collapse_id(self, mock_filter):
        """Chat pushes use the room tag so newer room notifications replace older ones."""
        ios_device = _make_device(device_id=12, device_type='ios', language='en')
        mock_filter.return_value = _make_qs([ios_device])

        noti = _make_message_notification(self.user, chat_room_id=123)

        from notification.models import notify_firebase
        notify_firebase(noti)

        sent_message = ios_device.send_message.call_args[0][0]
        messaging._MessagingService.encode_message(sent_message)
        _assert_ios_uses_collapse_tag(self, sent_message, 'chat_message_room_123')

    @patch('notification.models.CustomFCMDevice.objects.filter')
    def test_android_does_not_raise(self, mock_filter):
        """Android path should build a valid Message without errors."""
        android_device = _make_device(device_id=20, device_type='android', language='en')
        mock_filter.return_value = _make_qs([android_device])

        noti = _make_notification(self.user)

        from notification.models import notify_firebase
        notify_firebase(noti)

        android_device.send_message.assert_called_once()
        sent_message = android_device.send_message.call_args[0][0]
        self.assertEqual(sent_message.android.notification.title, 'WhoAmI Today')

    @patch('notification.models.send_msg_to_slack')
    @patch('notification.models.APNSConfig')
    @patch('notification.models.CustomFCMDevice.objects.filter')
    def test_ios_payload_error_does_not_block_other_devices(
        self, mock_filter, mock_apns_config, _mock_slack
    ):
        """A payload construction error for one device must not stop the send loop."""
        ios_device = _make_device(device_id=21, device_type='ios', language='en')
        android_device = _make_device(device_id=22, device_type='android', language='en')
        mock_filter.return_value = _make_qs([ios_device, android_device])
        mock_apns_config.side_effect = ValueError('bad apns payload')

        noti = _make_notification(self.user)

        from notification.models import notify_firebase
        notify_firebase(noti)

        ios_device.send_message.assert_not_called()
        android_device.send_message.assert_called_once()

    @patch('notification.models.CustomFCMDevice.objects.filter')
    def test_web_does_not_raise(self, mock_filter):
        """Web path should build a valid Message without errors."""
        web_device = _make_device(device_id=30, device_type='web', language='en')
        mock_filter.return_value = _make_qs([web_device])

        noti = _make_notification(self.user)

        from notification.models import notify_firebase
        notify_firebase(noti)

        web_device.send_message.assert_called_once()
        sent_message = web_device.send_message.call_args[0][0]
        self.assertEqual(sent_message.webpush.notification.title, 'WhoAmI Today')
