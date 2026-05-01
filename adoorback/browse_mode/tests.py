from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from browse_mode.models import BrowseModePreset, BrowseModeWishlistEntry

User = get_user_model()


VALID_CONFIG = {
    'tabs': ['friends', 'share'],
    'filters': {'friends_close_only': True},
    'sections': {},
}


class BrowseModePresetCRUDTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='pw'
        )
        self.other = User.objects.create_user(
            username='bob', email='bob@example.com', password='pw'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_preset(self):
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {'name': 'Hangout', 'config': VALID_CONFIG},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertTrue(BrowseModePreset.objects.filter(user=self.user, name='Hangout').exists())
        # default_battery is optional; defaults to None.
        self.assertIsNone(response.data['default_battery'])

    def test_create_preset_with_default_battery(self):
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {
                'name': 'Hangout',
                'config': VALID_CONFIG,
                'default_battery': 'moderately_social',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertEqual(response.data['default_battery'], 'moderately_social')

    def test_create_preset_rejects_invalid_default_battery(self):
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {
                'name': 'Hangout',
                'config': VALID_CONFIG,
                'default_battery': 'cosmic_glow',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_preset_strips_whitespace_from_name(self):
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {'name': '  Hangout  ', 'config': VALID_CONFIG},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Hangout')

    def test_create_preset_rejects_empty_name(self):
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {'name': '   ', 'config': VALID_CONFIG},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_preset_rejects_unknown_tab(self):
        bad_config = {**VALID_CONFIG, 'tabs': ['friends', 'mystery']}
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {'name': 'X', 'config': bad_config},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_preset_rejects_empty_tabs(self):
        bad_config = {**VALID_CONFIG, 'tabs': []}
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {'name': 'X', 'config': bad_config},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_preset_rejects_unknown_filter(self):
        bad_config = {**VALID_CONFIG, 'filters': {'nope': True}}
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {'name': 'X', 'config': bad_config},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_preset_rejects_legacy_feed_close_only_filter(self):
        # feed_close_only was a planned filter that never got wired to a
        # consumer; it's been removed from the allowed list to stay honest.
        bad_config = {**VALID_CONFIG, 'filters': {'feed_close_only': True}}
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {'name': 'X', 'config': bad_config},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_preset_rejects_non_boolean_section_value(self):
        bad_config = {**VALID_CONFIG, 'sections': {'hide_ping_buttons': 'yes'}}
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {'name': 'X', 'config': bad_config},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_name_rejected_per_user(self):
        BrowseModePreset.objects.create(user=self.user, name='Hangout', config=VALID_CONFIG)
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {'name': 'Hangout', 'config': VALID_CONFIG},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_name_allowed_across_users(self):
        BrowseModePreset.objects.create(user=self.other, name='Hangout', config=VALID_CONFIG)
        response = self.client.post(
            reverse('browse-mode-preset-list'),
            {'name': 'Hangout', 'config': VALID_CONFIG},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_list_only_returns_own_presets(self):
        BrowseModePreset.objects.create(user=self.user, name='Mine', config=VALID_CONFIG)
        BrowseModePreset.objects.create(user=self.other, name='Theirs', config=VALID_CONFIG)
        response = self.client.get(reverse('browse-mode-preset-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Response is paginated ({results: [...]}) on this project's DRF config.
        data = response.data
        items = data['results'] if isinstance(data, dict) and 'results' in data else data
        names = [p['name'] for p in items]
        self.assertIn('Mine', names)
        self.assertNotIn('Theirs', names)

    def test_update_preset(self):
        preset = BrowseModePreset.objects.create(
            user=self.user, name='Old', config=VALID_CONFIG
        )
        response = self.client.patch(
            reverse('browse-mode-preset-detail', args=[preset.id]),
            {'name': 'New'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        preset.refresh_from_db()
        self.assertEqual(preset.name, 'New')

    def test_cannot_update_other_users_preset(self):
        preset = BrowseModePreset.objects.create(
            user=self.other, name='Theirs', config=VALID_CONFIG
        )
        response = self.client.patch(
            reverse('browse-mode-preset-detail', args=[preset.id]),
            {'name': 'Hijacked'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_preset(self):
        preset = BrowseModePreset.objects.create(
            user=self.user, name='Bye', config=VALID_CONFIG
        )
        response = self.client.delete(
            reverse('browse-mode-preset-detail', args=[preset.id])
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(BrowseModePreset.objects.filter(id=preset.id).exists())

    def test_mark_used_bumps_last_used_at(self):
        preset = BrowseModePreset.objects.create(
            user=self.user, name='Hangout', config=VALID_CONFIG
        )
        self.assertIsNone(preset.last_used_at)
        response = self.client.post(
            reverse('browse-mode-preset-mark-used', args=[preset.id])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        preset.refresh_from_db()
        self.assertIsNotNone(preset.last_used_at)

    def test_mark_used_requires_ownership(self):
        preset = BrowseModePreset.objects.create(
            user=self.other, name='Theirs', config=VALID_CONFIG
        )
        response = self.client.post(
            reverse('browse-mode-preset-mark-used', args=[preset.id])
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_blocked(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse('browse-mode-preset-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_preset_rejects_my_or_questions_tab(self):
        for forbidden in ('my', 'questions'):
            bad_config = {**VALID_CONFIG, 'tabs': ['friends', forbidden]}
            response = self.client.post(
                reverse('browse-mode-preset-list'),
                {'name': f'X-{forbidden}', 'config': bad_config},
                format='json',
            )
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"{forbidden} should be rejected",
            )


class BrowseModeWishlistTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='pw'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_wishlist_entry(self):
        response = self.client.post(
            reverse('browse-mode-wishlist-create'),
            {'content': 'Hide reactions during work hours please'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(BrowseModeWishlistEntry.objects.filter(user=self.user).count(), 1)

    def test_wishlist_entry_strips_whitespace(self):
        response = self.client.post(
            reverse('browse-mode-wishlist-create'),
            {'content': '   really cool idea   '},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entry = BrowseModeWishlistEntry.objects.get(user=self.user)
        self.assertEqual(entry.content, 'really cool idea')

    def test_wishlist_rejects_empty(self):
        response = self.client.post(
            reverse('browse-mode-wishlist-create'),
            {'content': '   '},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wishlist_rejects_overlong(self):
        response = self.client.post(
            reverse('browse-mode-wishlist-create'),
            {'content': 'x' * 2001},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wishlist_unauthenticated_blocked(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            reverse('browse-mode-wishlist-create'),
            {'content': 'hi'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
