from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Q
from django.test import TestCase

from chat.models import ChatRoom, Message, OnboardingScreenshot
from chat import wit_bot_state as state_mod

User = get_user_model()


class EngineDispatchTests(TestCase):
    def setUp(self):
        # Operators (so the wit_admin auto-provision succeeds) + alice.
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(
            username='alice', email='a@e.com', password='x',
        )
        self.alice.current_ver = 'version_w'
        self.alice.save(update_fields=['current_ver'])

        from chat.wit_bot import ensure_wit_bot_user
        self.bot = ensure_wit_bot_user()
        self.room = ChatRoom.objects.get(
            (Q(user1=self.alice) & Q(user2=self.bot))
            | (Q(user1=self.bot) & Q(user2=self.alice))
        )

    # ---------- helpers ----------

    def _send_choice(self, payload):
        return Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=self.bot,
            content=payload, bot_payload={'kind': 'choice', 'payload': payload},
        )

    def _send_text(self, text):
        return Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=self.bot,
            content=text,
        )

    def _send_multi_select_response(self, intent, selected):
        return Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=self.bot,
            content='multi-select submitted',
            bot_payload={
                'kind': 'multi_select_response',
                'intent': intent,
                'selected': selected,
            },
        )

    def _bot_replies(self):
        return Message.objects.filter(chat_room=self.room, sender=self.bot)

    def _add_friend_for_alice(self):
        from account.models import Connection
        bob = User.objects.create_user(username='bob', email='bob@e.com', password='x')
        smaller, larger = (self.alice, bob) if self.alice.id < bob.id else (bob, self.alice)
        choice = 'friend'
        Connection.objects.create(
            user1=smaller, user2=larger,
            user1_choice=choice, user2_choice=choice,
        )
        return bob

    def _enable_push_for_alice(self):
        from custom_fcm.models import CustomFCMDevice
        return CustomFCMDevice.objects.create(
            user=self.alice, registration_id='abc', type='ios', active=True,
        )

    def _walk_through_quizzes(self):
        """Drive the conversation through quizzes 1, 2, 3 with all-correct answers.
        After return, the engine has executed kickoff_quiz_3 → which auto-runs
        through push, friend, widget entry depending on env state.
        """
        from chat.wit_bot_copy import QUIZ_1_STUDY_REQUIREMENTS as q1
        self._send_choice('start_onboarding')
        self._send_choice('kickoff_welcome_continue')
        self._send_multi_select_response(
            'kickoff_quiz_1',
            [o['value'] for o in q1['options'] if o['correct']],
        )
        self._send_choice('q2:correct')
        self._send_choice('q3:sidebar')

    # ---------- Dispatch baseline ----------

    def test_admin_choice_still_escalates(self):
        before = self._bot_replies().count()
        self._send_choice('admin')
        self.assertGreater(self._bot_replies().count(), before)
        self.room.refresh_from_db()
        self.assertTrue(self.room.is_group)

    def test_start_onboarding_enters_kickoff_welcome(self):
        self._send_choice('start_onboarding')
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'kickoff_welcome')

    def test_unknown_text_idle_response(self):
        before = self._bot_replies().count()
        self._send_text('huh')
        self.assertGreater(self._bot_replies().count(), before)

    # ---------- Task 7 — kickoff_welcome ----------

    def test_kickoff_welcome_continue_advances_to_quiz_1(self):
        self._send_choice('start_onboarding')
        self._send_choice('kickoff_welcome_continue')
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'kickoff_quiz_1')
        # Find the multi_select message (latest non-welcome-card reply)
        multi_select_msgs = self._bot_replies().exclude(
            event_type='wit_welcome_card',
        ).order_by('-created_at')
        latest = multi_select_msgs.first()
        self.assertEqual(latest.bot_payload.get('kind'), 'multi_select')
        self.assertEqual(latest.bot_payload.get('intent'), 'kickoff_quiz_1')

    # ---------- Task 8 — kickoff_quiz_1 ----------

    def test_quiz_1_perfect_score_advances_to_quiz_2(self):
        self._send_choice('start_onboarding')
        self._send_choice('kickoff_welcome_continue')
        from chat.wit_bot_copy import QUIZ_1_STUDY_REQUIREMENTS as q
        correct_values = [o['value'] for o in q['options'] if o['correct']]
        self._send_multi_select_response('kickoff_quiz_1', correct_values)
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'kickoff_quiz_2')
        prog = state_mod.progress_for(state, 'version_w')
        self.assertGreaterEqual(prog['kickoff']['quiz_1']['score'], 0.99)

    def test_quiz_1_partial_advances_anyway(self):
        self._send_choice('start_onboarding')
        self._send_choice('kickoff_welcome_continue')
        self._send_multi_select_response('kickoff_quiz_1', ['pre_study'])
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'kickoff_quiz_2')
        prog = state_mod.progress_for(state, 'version_w')
        self.assertLess(prog['kickoff']['quiz_1']['score'], 0.99)

    # ---------- Task 9 — kickoff_quiz_2 ----------

    def test_quiz_2_correct_advances_to_quiz_3(self):
        self._send_choice('start_onboarding')
        self._send_choice('kickoff_welcome_continue')
        from chat.wit_bot_copy import QUIZ_1_STUDY_REQUIREMENTS as q1
        self._send_multi_select_response(
            'kickoff_quiz_1',
            [o['value'] for o in q1['options'] if o['correct']],
        )
        self._send_choice('q2:correct')
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'kickoff_quiz_3')
        prog = state_mod.progress_for(state, 'version_w')
        self.assertTrue(prog['kickoff']['quiz_2']['correct'])

    def test_quiz_2_wrong_re_prompts(self):
        self._send_choice('start_onboarding')
        self._send_choice('kickoff_welcome_continue')
        from chat.wit_bot_copy import QUIZ_1_STUDY_REQUIREMENTS as q1
        self._send_multi_select_response(
            'kickoff_quiz_1',
            [o['value'] for o in q1['options'] if o['correct']],
        )
        self._send_choice('q2:gemini')
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'kickoff_quiz_2')
        prog = state_mod.progress_for(state, 'version_w')
        self.assertEqual(prog['kickoff']['quiz_2']['attempts'], 1)

    # ---------- Task 10 — kickoff_quiz_3 ----------

    def test_quiz_3_correct_advances_through_setup_checks(self):
        """With no FCM device + no friends, after q3:sidebar the engine ends at kickoff_push
        (waiting for user to enable notifs)."""
        self._walk_through_quizzes()
        state = state_mod.get_or_create_state(self.alice)
        # Push check fails → state stays at kickoff_push
        self.assertEqual(state.current_intent, 'kickoff_push')

    # ---------- Task 11 — kickoff_push ----------

    def test_push_with_active_device_advances_to_friend(self):
        self._enable_push_for_alice()
        self._walk_through_quizzes()
        state = state_mod.get_or_create_state(self.alice)
        # Push passes; friend check fails (no friend) → state stays at kickoff_friend
        self.assertEqual(state.current_intent, 'kickoff_friend')

    def test_push_done_tap_rechecks_and_advances(self):
        self._walk_through_quizzes()
        # Now turn on a device and tap Done
        self._enable_push_for_alice()
        self._send_choice('kickoff_push_done')
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'kickoff_friend')

    # ---------- Task 12 — kickoff_friend ----------

    def test_friend_with_connection_advances_to_widget(self):
        self._enable_push_for_alice()
        self._add_friend_for_alice()
        self._walk_through_quizzes()
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'kickoff_widget')

    def test_friend_done_after_adding_advances(self):
        self._enable_push_for_alice()
        self._walk_through_quizzes()
        # Should be at kickoff_friend now
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'kickoff_friend')
        # Add a friend, tap Done
        self._add_friend_for_alice()
        self._send_choice('kickoff_friend_done')
        state.refresh_from_db()
        self.assertEqual(state.current_intent, 'kickoff_widget')

    # ---------- Task 13 — kickoff_widget ----------

    # ---------- Task 15 — welcome card refresh ----------

    def test_welcome_card_refreshes_on_user_message(self):
        self._send_choice('start_onboarding')
        welcome_msgs = Message.objects.filter(
            chat_room=self.room, event_type='wit_welcome_card',
        )
        self.assertEqual(welcome_msgs.count(), 1)
        # CTA should now be Resume since we're mid-flow
        labels = [b['label'] for b in welcome_msgs.first().bot_payload['buttons']]
        self.assertIn('Resume onboarding', labels)

    # ---------- V1.1 — Audit handler ----------

    def _complete_kickoff(self):
        """Mark kickoff complete in state, return to idle."""
        state = state_mod.get_or_create_state(self.alice)
        state_mod.set_intent(state, '', step=0)
        state_mod.set_progress(state, 'version_w', 'kickoff', {'completed': True})

    def test_run_audit_from_idle_enters_audit(self):
        self._complete_kickoff()
        self._send_choice('run_audit')
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'audit')
        # Bot replied with header + result body
        replies = self._bot_replies().exclude(event_type='wit_welcome_card')
        latest = replies.order_by('-created_at').first()
        self.assertIn('not yet', latest.content.lower())

    def test_audit_walkthrough_button_enters_walkthrough(self):
        self._complete_kickoff()
        self._send_choice('run_audit')
        self._send_choice('audit_walkthrough')
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'walkthrough')

    def test_audit_just_list_returns_to_idle(self):
        self._complete_kickoff()
        self._send_choice('run_audit')
        self._send_choice('audit_just_list')
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, '')

    def test_audit_later_returns_to_idle(self):
        self._complete_kickoff()
        self._send_choice('run_audit')
        self._send_choice('audit_later')
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, '')

    # ---------- V1.1 — Walkthrough handler ----------

    def test_walkthrough_done_logs_self_report_and_advances(self):
        from chat.models import OnboardingEvent
        self._complete_kickoff()
        self._send_choice('run_audit')
        self._send_choice('audit_walkthrough')
        # State now has missing list, index=0
        state = state_mod.get_or_create_state(self.alice)
        prog = state_mod.progress_for(state, 'version_w')
        first_key = prog['walkthrough']['missing_keys'][0]

        before_count = OnboardingEvent.objects.filter(
            user=self.alice, event_key=f'self_report:{first_key}',
        ).count()
        self._send_choice(f'walkthrough_done:{first_key}')

        after_count = OnboardingEvent.objects.filter(
            user=self.alice, event_key=f'self_report:{first_key}',
        ).count()
        self.assertEqual(after_count, before_count + 1)

        state.refresh_from_db()
        prog = state_mod.progress_for(state, 'version_w')
        self.assertEqual(prog['walkthrough']['index'], 1)

    def test_walkthrough_skip_advances_no_event(self):
        from chat.models import OnboardingEvent
        self._complete_kickoff()
        self._send_choice('run_audit')
        self._send_choice('audit_walkthrough')
        state = state_mod.get_or_create_state(self.alice)
        prog = state_mod.progress_for(state, 'version_w')
        first_key = prog['walkthrough']['missing_keys'][0]

        before = OnboardingEvent.objects.filter(user=self.alice).count()
        self._send_choice(f'walkthrough_skip:{first_key}')
        after = OnboardingEvent.objects.filter(user=self.alice).count()
        self.assertEqual(after, before)

        state.refresh_from_db()
        prog = state_mod.progress_for(state, 'version_w')
        self.assertEqual(prog['walkthrough']['index'], 1)

    # ---------- Task 13 — kickoff_widget ----------

    def test_widget_screenshot_creates_record_and_completes(self):
        self._enable_push_for_alice()
        self._add_friend_for_alice()
        self._walk_through_quizzes()
        # State should now be at kickoff_widget
        # Submit a fake image upload
        img = SimpleUploadedFile('widget.png', b'fake-png-bytes', content_type='image/png')
        Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=self.bot,
            content='widget upload', image=img,
            bot_payload={'kind': 'upload_response', 'context': 'widget'},
        )
        self.assertEqual(
            OnboardingScreenshot.objects.filter(user=self.alice, kind='widget').count(),
            1,
        )
        state = state_mod.get_or_create_state(self.alice)
        # Back to idle (kickoff complete)
        self.assertEqual(state.current_intent, '')
        prog = state_mod.progress_for(state, 'version_w')
        self.assertTrue(prog['kickoff']['completed'])
