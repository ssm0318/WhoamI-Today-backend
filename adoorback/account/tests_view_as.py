from django.test import RequestFactory, TestCase
from rest_framework.exceptions import ValidationError
from account.view_as import parse_view_as, VIEW_AS_TIERS


class ParseViewAsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_returns_none_when_param_missing(self):
        request = self.factory.get('/api/user/me/')
        self.assertIsNone(parse_view_as(request))

    def test_returns_tier_when_valid(self):
        for tier in VIEW_AS_TIERS:
            request = self.factory.get(f'/api/user/me/?view_as={tier}')
            self.assertEqual(parse_view_as(request), tier)

    def test_raises_validation_error_when_invalid(self):
        request = self.factory.get('/api/user/me/?view_as=enemies')
        with self.assertRaises(ValidationError):
            parse_view_as(request)
