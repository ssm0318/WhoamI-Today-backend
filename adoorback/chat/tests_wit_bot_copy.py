from django.test import SimpleTestCase

from chat import wit_bot_copy as copy


class CopyShapeTests(SimpleTestCase):
    def test_quiz_1_has_correct_and_absurd_options(self):
        q = copy.QUIZ_1_STUDY_REQUIREMENTS
        labels = [opt['label'] for opt in q['options']]
        self.assertIn('Pre-study survey', labels)
        self.assertIn('Daily surveys', labels)
        self.assertIn('Win the lottery', labels)
        for opt in q['options']:
            self.assertIn('correct', opt)
            self.assertIsInstance(opt['correct'], bool)

    def test_quiz_2_has_one_correct_single_select(self):
        q = copy.QUIZ_2_SWAP_TIMING
        correct = [o for o in q['options'] if o['correct']]
        self.assertEqual(len(correct), 1)
        self.assertEqual(correct[0]['label'], 'Midnight May 17 → 18 PST')

    def test_quiz_3_has_one_correct_single_select(self):
        q = copy.QUIZ_3_SURVEYS_LOCATION
        correct = [o for o in q['options'] if o['correct']]
        self.assertEqual(len(correct), 1)

    def test_witty_voice_has_required_fragments(self):
        self.assertIn('WITty', copy.WELCOME_INTRO)
        self.assertIn('ha. ha. ha.', copy.WELCOME_INTRO)
