from django.test import SimpleTestCase

from chat import wit_bot_copy as copy


class CopyShapeTests(SimpleTestCase):
    def test_quiz_1_has_correct_and_absurd_options(self):
        q = copy.QUIZ_1_STUDY_REQUIREMENTS
        en_labels = [copy.t(opt['label'], 'en') for opt in q['options']]
        ko_labels = [copy.t(opt['label'], 'ko') for opt in q['options']]
        self.assertIn('Pre-study survey', en_labels)
        self.assertIn('사전 설문조사', ko_labels)
        self.assertIn('Win the lottery', en_labels)
        for opt in q['options']:
            self.assertIn('correct', opt)
            self.assertIsInstance(opt['correct'], bool)

    def test_quiz_2_has_one_correct_single_select(self):
        q = copy.QUIZ_2_SWAP_TIMING
        correct = [o for o in q['options'] if o['correct']]
        self.assertEqual(len(correct), 1)
        self.assertEqual(copy.t(correct[0]['label'], 'en'), 'Midnight May 17 → 18 PST')
        self.assertEqual(copy.t(correct[0]['label'], 'ko'), 'PST 5월 17→18 자정')

    def test_quiz_3_has_one_correct_single_select(self):
        q = copy.QUIZ_3_SURVEYS_LOCATION
        correct = [o for o in q['options'] if o['correct']]
        self.assertEqual(len(correct), 1)

    def test_witty_voice_has_required_fragments(self):
        self.assertIn('WITty', copy.t(copy.WELCOME_INTRO, 'en'))
        self.assertIn('ha. ha. ha.', copy.t(copy.WELCOME_INTRO, 'en'))
        self.assertIn('WITty', copy.t(copy.WELCOME_INTRO, 'ko'))
        self.assertIn('하. 하. 하.', copy.t(copy.WELCOME_INTRO, 'ko'))

    def test_t_resolver_falls_back_to_en(self):
        d = {'en': 'hello', 'ko': '안녕'}
        self.assertEqual(copy.t(d, 'en'), 'hello')
        self.assertEqual(copy.t(d, 'ko'), '안녕')
        # Unknown lang falls back
        self.assertEqual(copy.t(d, 'fr'), 'hello')
        # Unknown lang on dict without en falls back to ''
        self.assertEqual(copy.t({'ko': '안녕'}, 'fr'), '')
        # Non-dict passes through unchanged
        self.assertEqual(copy.t('plain string', 'ko'), 'plain string')

    def test_t_resolver_accepts_user_with_language(self):
        class FakeUser:
            language = 'ko'
        self.assertEqual(copy.t({'en': 'hi', 'ko': '안녕'}, FakeUser()), '안녕')

    def test_all_faq_entries_have_both_languages(self):
        for entry in copy.FAQ_ENTRIES:
            self.assertIn('en', entry['question'])
            self.assertIn('ko', entry['question'])
            self.assertIn('en', entry['answer'])
            self.assertIn('ko', entry['answer'])
            self.assertTrue(copy.t(entry['question'], 'ko'))
            self.assertTrue(copy.t(entry['answer'], 'ko'))

    def test_wit_replies_have_both_languages(self):
        self.assertGreaterEqual(len(copy.WIT_REPLIES), 5)
        for reply in copy.WIT_REPLIES:
            self.assertIn('en', reply)
            self.assertIn('ko', reply)
