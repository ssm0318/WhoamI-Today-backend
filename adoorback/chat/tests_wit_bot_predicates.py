from django.contrib.auth import get_user_model
from django.test import TestCase

from chat.models import OnboardingEvent
from chat import wit_bot_predicates as p

User = get_user_model()


class PredicateRegistryTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username='alice', email='a@e.com', password='x',
        )
        self.alice.current_ver = 'version_w'
        self.alice.save(update_fields=['current_ver'])

    def test_predicates_for_w_excludes_q_only(self):
        w = p.predicates_for('version_w')
        keys = {pr.feature_key for pr in w}
        self.assertIn('checkin_battery', keys)
        self.assertIn('private_comment', keys)
        self.assertNotIn('checkin_post', keys)
        self.assertNotIn('q_feed_visit', keys)

    def test_predicates_for_q_excludes_w_only(self):
        q = p.predicates_for('version_q')
        keys = {pr.feature_key for pr in q}
        self.assertIn('checkin_post', keys)
        self.assertIn('q_feed_visit', keys)
        self.assertIn('my_tab_visit', keys)
        self.assertNotIn('checkin_battery', keys)
        self.assertNotIn('browse_mode', keys)

    def test_predicate_by_key(self):
        pred = p.predicate_by_key('checkin_mood')
        self.assertIsNotNone(pred)
        self.assertEqual(pred.kind, 'db')

        self.assertIsNone(p.predicate_by_key('nonexistent'))

    def test_event_predicate_negative_then_positive(self):
        pred = p.predicate_by_key('view_as')
        self.assertFalse(pred.is_engaged(self.alice))
        OnboardingEvent.objects.create(
            user=self.alice, version='version_w',
            event_key='view_as_picker_opened',
        )
        self.assertTrue(pred.is_engaged(self.alice))

    def test_event_predicate_uses_current_version_only(self):
        pred = p.predicate_by_key('discover_visit')
        OnboardingEvent.objects.create(
            user=self.alice, version='version_w',
            event_key='discover_opened',
        )
        self.alice.current_ver = 'version_q'
        self.alice.save(update_fields=['current_ver'])
        self.assertFalse(pred.is_engaged(self.alice))

    def test_browse_mode_customize_open_counts_as_engagement(self):
        pred = p.predicate_by_key('browse_mode')
        self.assertFalse(pred.is_engaged(self.alice))
        OnboardingEvent.objects.create(
            user=self.alice, version='version_w',
            event_key='browse_mode_customize_opened',
            payload={'source': 'new'},
        )
        self.assertTrue(pred.is_engaged(self.alice))

    def test_browse_mode_customize_open_uses_current_version_only(self):
        pred = p.predicate_by_key('browse_mode')
        OnboardingEvent.objects.create(
            user=self.alice, version='version_w',
            event_key='browse_mode_customize_opened',
            payload={'source': 'new'},
        )
        self.alice.current_ver = 'version_q'
        self.alice.save(update_fields=['current_ver'])
        self.assertFalse(pred.is_engaged(self.alice))

    def test_walkthrough_predicates_have_take_me_there_links(self):
        missing_links = [
            pred.feature_key
            for pred in p.PREDICATES
            if pred.deep_link is None
        ]
        self.assertEqual(missing_links, [])

    def test_walkthrough_deep_links_route_to_feature_entry_points(self):
        expected = {
            'browse_mode': '/discover?browse_mode=customize',
            'private_comment': '/discover',
            'reaction': '/discover',
            'subscribe_bell': '/friends',
            'photo_of_day': '/share/photo',
            'checkin_battery': '/update?editor=battery',
            'checkin_mood': '/update?editor=mood',
            'checkin_thought': '/update?editor=thought',
            'checkin_song': '/update?editor=song',
            'profile_chips': '/settings/edit-profile',
            'pinned_checkin': '/update?tab=history',
            'checkin_post': '/check-in-posts/new',
        }
        for feature_key, deep_link in expected.items():
            self.assertEqual(p.predicate_by_key(feature_key).deep_link, deep_link)

    def test_subscribe_bell_walkthrough_link_matches_current_version(self):
        pred = p.predicate_by_key('subscribe_bell')
        self.assertEqual(pred.deep_link_for('version_w'), '/friends')
        self.assertEqual(pred.deep_link_for('version_q'), '/my/friends/list')

    def test_subscribe_bell_walkthrough_copy_matches_current_version(self):
        pred = p.predicate_by_key('subscribe_bell')
        self.assertIn('Open Friends', pred.description_for('version_w'))
        self.assertIn('My tab friend list', pred.description_for('version_q'))

    def test_db_predicate_non_public_account(self):
        pred = p.predicate_by_key('non_public_account')
        self.assertFalse(pred.is_engaged(self.alice))
        self.alice.is_public = False
        self.alice.save(update_fields=['is_public'])
        self.assertTrue(pred.is_engaged(self.alice))

    def test_db_predicate_checkin_battery(self):
        pred = p.predicate_by_key('checkin_battery')
        self.assertFalse(pred.is_engaged(self.alice))
        from check_in.models import CheckInComponentEntry
        CheckInComponentEntry.objects.create(
            owner=self.alice, component='battery',
            visibility='friends', data={'value': 50},
        )
        self.assertTrue(pred.is_engaged(self.alice))

    def test_all_predicates_have_required_metadata(self):
        for pred in p.PREDICATES:
            self.assertTrue(pred.feature_key, f"{pred} missing feature_key")
            self.assertTrue(pred.display_name)
            self.assertTrue(pred.description)
            self.assertIn(pred.kind, ('db', 'event', 'self_report'))
            self.assertTrue(pred.versions)
