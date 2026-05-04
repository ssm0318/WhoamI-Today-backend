from django.test import SimpleTestCase

from chat import wit_bot_payloads as p


class PayloadBuilderTests(SimpleTestCase):
    def test_card_with_buttons(self):
        payload = p.card_with_buttons([
            {'label': 'Yes', 'payload': 'yes'},
            {'label': 'No', 'payload': 'no'},
        ])
        self.assertEqual(payload['kind'], 'card')
        self.assertEqual(len(payload['buttons']), 2)
        self.assertEqual(payload['buttons'][0]['action'], 'reply')

    def test_multi_select(self):
        payload = p.multi_select(
            intent='kickoff_quiz_1',
            options=[
                {'label': 'A', 'value': 'a'},
                {'label': 'B', 'value': 'b'},
            ],
        )
        self.assertEqual(payload['kind'], 'multi_select')
        self.assertEqual(payload['intent'], 'kickoff_quiz_1')
        self.assertEqual(len(payload['options']), 2)
        self.assertEqual(payload['submit_label'], 'Submit')

    def test_upload_request(self):
        payload = p.upload_request(context='widget')
        self.assertEqual(payload['kind'], 'upload')
        self.assertEqual(payload['context'], 'widget')

    def test_navigate_button(self):
        payload = p.card_with_buttons([
            {'label': 'Take me there', 'navigate_to': '/surveys'},
        ])
        self.assertEqual(payload['buttons'][0]['action'], 'navigate')
        self.assertEqual(payload['buttons'][0]['url'], '/surveys')
