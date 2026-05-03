"""
Tests for notify_firebase – Firebase push notification message construction.

These tests use unittest.mock so no real Firebase credentials are needed.
Run with:
    python manage.py test notification.tests
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from firebase_admin._messaging_utils import ApsAlert


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
    from unittest.mock import PropertyMock
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


class NotifyFirebaseIosAlertTest(TestCase):
    """
    Ensures that the iOS APNS message is built with ApsAlert (not a plain dict),
    which is what caused the ValueError in production.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='pw'
        )

    @patch('notification.models.CustomFCMDevice.objects.filter')
    def test_ios_alert_is_aps_alert_instance(self, mock_filter):
        """The Aps.alert field must be an ApsAlert, not a dict."""
        ios_device = _make_device(device_id=10, device_type='ios', language='en')
        mock_filter.return_value = _make_qs([ios_device])

        noti = _make_notification(self.user, message_en='You got a like!', message_ko='좋아요 받았어요!')

        from notification.models import notify_firebase
        notify_firebase(noti)

        # send_message must have been called exactly once
        ios_device.send_message.assert_called_once()
        sent_message = ios_device.send_message.call_args[0][0]

        # Drill into the built Message object
        aps = sent_message.apns.payload.aps
        self.assertIsInstance(
            aps.alert,
            ApsAlert,
            f"Expected ApsAlert instance, got {type(aps.alert)}: {aps.alert!r}\n"
            "This is the bug that caused the ValueError in production."
        )
        self.assertEqual(aps.alert.title, 'WhoAmI Today')
        self.assertEqual(aps.alert.body, 'You got a like!')

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
        self.assertEqual(aps.alert.body, '좋아요 받았어요!')

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
