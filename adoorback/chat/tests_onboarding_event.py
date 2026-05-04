from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from chat.models import OnboardingEvent

User = get_user_model()


class OnboardingEventEndpointTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username='alice', email='a@e.com', password='x',
        )
        self.alice.current_ver = 'version_w'
        self.alice.save(update_fields=['current_ver'])
        self.client = APIClient()
        self.client.force_authenticate(user=self.alice)

    def test_post_creates_event(self):
        resp = self.client.post(
            '/api/chat/onboarding-events/',
            {'event_key': 'browse_mode_toggled', 'payload': {'new_state': 'social'}},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            OnboardingEvent.objects.filter(user=self.alice, event_key='browse_mode_toggled').count(),
            1,
        )
        ev = OnboardingEvent.objects.get(user=self.alice, event_key='browse_mode_toggled')
        self.assertEqual(ev.version, 'version_w')
        self.assertEqual(ev.payload, {'new_state': 'social'})

    def test_post_without_event_key_fails(self):
        resp = self.client.post(
            '/api/chat/onboarding-events/',
            {'payload': {'x': 1}},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_with_empty_payload_works(self):
        resp = self.client.post(
            '/api/chat/onboarding-events/',
            {'event_key': 'view_as_picker_opened'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        ev = OnboardingEvent.objects.get(user=self.alice, event_key='view_as_picker_opened')
        self.assertEqual(ev.payload, {})

    def test_unauthenticated_blocked(self):
        anon = APIClient()
        resp = anon.post(
            '/api/chat/onboarding-events/',
            {'event_key': 'foo'},
            format='json',
        )
        self.assertIn(resp.status_code, (401, 403))
