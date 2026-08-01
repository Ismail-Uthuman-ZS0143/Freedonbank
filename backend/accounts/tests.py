from django.contrib.auth.models import User
from django.urls import reverse_lazy
from rest_framework.test import APITestCase
from rest_framework import status

from .models import LoginEvent

LOGIN_URL = '/api/auth/login'
LOGOUT_URL = '/api/auth/logout'
ME_URL = '/api/auth/me'


class LoginTests(APITestCase):
    def setUp(self):
        self.password = 'Freedom2026!'
        self.user = User.objects.create_user(
            username='banker@freedombankva.com',
            email='banker@freedombankva.com',
            password=self.password,
            first_name='Dana',
            last_name='Whitfield',
        )

    def test_login_success_returns_user_and_sets_session(self):
        res = self.client.post(LOGIN_URL, {'email': 'banker@freedombankva.com', 'password': self.password}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['user']['email'], 'banker@freedombankva.com')
        self.assertEqual(res.data['user']['fullName'], 'Dana Whitfield')

        # Session cookie from login should authenticate the very next request.
        me_res = self.client.get(ME_URL)
        self.assertEqual(me_res.data['user']['email'], 'banker@freedombankva.com')

    def test_login_is_case_insensitive_on_email(self):
        res = self.client.post(LOGIN_URL, {'email': 'BANKER@FREEDOMBANKVA.COM', 'password': self.password}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_login_wrong_password_rejected(self):
        res = self.client.post(LOGIN_URL, {'email': 'banker@freedombankva.com', 'password': 'wrong'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('error', res.data)

    def test_login_unknown_email_rejected(self):
        res = self.client.post(LOGIN_URL, {'email': 'nobody@freedombankva.com', 'password': 'whatever'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_wrong_password_and_unknown_email_give_identical_error(self):
        """Don't leak whether the account exists via a different error message."""
        wrong_pw = self.client.post(LOGIN_URL, {'email': 'banker@freedombankva.com', 'password': 'wrong'}, format='json')
        unknown = self.client.post(LOGIN_URL, {'email': 'nobody@freedombankva.com', 'password': 'wrong'}, format='json')
        self.assertEqual(wrong_pw.data['error'], unknown.data['error'])

    def test_login_missing_email_rejected(self):
        res = self.client.post(LOGIN_URL, {'password': self.password}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_missing_password_rejected(self):
        res = self.client.post(LOGIN_URL, {'email': 'banker@freedombankva.com'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        res = self.client.post(LOGIN_URL, {'email': 'banker@freedombankva.com', 'password': self.password}, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class MeEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='banker@freedombankva.com', email='banker@freedombankva.com', password='Freedom2026!')

    def test_me_returns_null_when_not_signed_in(self):
        res = self.client.get(ME_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsNone(res.data['user'])

    def test_me_returns_user_after_login(self):
        self.client.post(LOGIN_URL, {'email': 'banker@freedombankva.com', 'password': 'Freedom2026!'}, format='json')
        res = self.client.get(ME_URL)
        self.assertEqual(res.data['user']['email'], 'banker@freedombankva.com')


class LogoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='banker@freedombankva.com', email='banker@freedombankva.com', password='Freedom2026!')

    def test_logout_requires_authentication(self):
        res = self.client.post(LOGOUT_URL)
        # DRF's SessionAuthentication has no WWW-Authenticate challenge, so an
        # unauthenticated IsAuthenticated view returns 403, not 401.
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_logout_clears_session(self):
        self.client.post(LOGIN_URL, {'email': 'banker@freedombankva.com', 'password': 'Freedom2026!'}, format='json')
        logout_res = self.client.post(LOGOUT_URL)
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

        me_res = self.client.get(ME_URL)
        self.assertIsNone(me_res.data['user'])


class LoginAuditTests(APITestCase):
    """Every sign-in attempt (success or failure) must be recorded -- matches
    the product requirement 'every sign-in audited'."""

    def setUp(self):
        self.user = User.objects.create_user(username='banker@freedombankva.com', email='banker@freedombankva.com', password='Freedom2026!')

    def test_successful_login_creates_audit_event(self):
        self.client.post(LOGIN_URL, {'email': 'banker@freedombankva.com', 'password': 'Freedom2026!'}, format='json')
        event = LoginEvent.objects.get(email_attempted='banker@freedombankva.com', success=True)
        self.assertEqual(event.user, self.user)

    def test_failed_login_creates_audit_event(self):
        self.client.post(LOGIN_URL, {'email': 'banker@freedombankva.com', 'password': 'wrong'}, format='json')
        event = LoginEvent.objects.get(email_attempted='banker@freedombankva.com', success=False)
        self.assertIsNone(event.user)

    def test_login_attempt_for_unknown_email_still_logged(self):
        self.client.post(LOGIN_URL, {'email': 'ghost@freedombankva.com', 'password': 'x'}, format='json')
        self.assertTrue(LoginEvent.objects.filter(email_attempted='ghost@freedombankva.com', success=False).exists())

    def test_malformed_request_does_not_create_audit_event(self):
        """Missing email/password is a 400 (client error) before we even
        attempt authentication -- nothing meaningful to audit yet."""
        before = LoginEvent.objects.count()
        self.client.post(LOGIN_URL, {}, format='json')
        self.assertEqual(LoginEvent.objects.count(), before)

    def test_audit_log_is_read_only_via_admin(self):
        """Sanity check on the admin registration: no add/change permission,
        since this is meant to be an append-only trail."""
        from django.contrib import admin
        from .models import LoginEvent as LE
        model_admin = admin.site._registry[LE]
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_change_permission(None))
