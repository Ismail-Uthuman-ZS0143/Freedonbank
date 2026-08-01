import io
import os
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings, TestCase
from rest_framework.test import APITestCase
from rest_framework import status

from .models import (
    DocumentRequest, RequestEmail, ChecklistItem, UploadedFile, UploadSession,
    DocumentTwin, BusinessTwin, ExtractionEvent, ExtractedValue, ChecklistPreference,
)
from . import checklist as checklist_module
from . import content_extraction
from . import mail_delivery

VALIDATE_URL = '/api/requests/validate'
LIST_CREATE_URL = '/api/requests'

# A small, fixed, all-Lender selection used by most tests -- real items from
# checklist.CHECKLIST_TEMPLATE (so `_resolve_selected_items` accepts them),
# just fewer of them than the real ~27-item default so upload-mechanics
# tests stay fast and every item in `.checklist_items.all()` is uploadable.
# Tests that specifically exercise the Lender/Loan Admin split or the real
# default selection use `checklist_module.default_selection()` directly.
TEST_CHECKLIST_SELECTION = [
    {'category': 'Organizational documents / financial info', 'name': 'Corporate Resolution'},
    {'category': 'Organizational documents / financial info', 'name': 'Personal Financial Statements'},
    {'category': 'Initial loan documents', 'name': 'Loan Presentation / Submission'},
]
TEST_CHECKLIST_NAMES = [item['name'] for item in TEST_CHECKLIST_SELECTION]

# Django's TestCase only sandboxes the DB (rolled back per test) -- disk
# writes from storage.py are NOT sandboxed, so without this every test run
# would leave real files behind in the actual UPLOAD_STORAGE_ROOT. Redirect
# to a throwaway temp dir for the whole module instead.
_test_upload_dir = tempfile.TemporaryDirectory(prefix='cfs2_test_uploads_')
_upload_root_override = override_settings(UPLOAD_STORAGE_ROOT=_test_upload_dir.name)

# Real email delivery (mail_delivery.py) fails closed on an empty
# MAIL_ALLOWED_DOMAINS by default, so tests never hit the real network as
# long as .env doesn't set one -- but that's an implicit guarantee this
# module shouldn't depend on. Force MAIL_ENABLED off explicitly so a future
# .env change can never turn a test run into a flaky network-dependent one.
_mail_disabled_override = override_settings(MAIL_ENABLED=False)


def setUpModule():
    _upload_root_override.enable()
    _mail_disabled_override.enable()


def tearDownModule():
    _upload_root_override.disable()
    _test_upload_dir.cleanup()
    _mail_disabled_override.disable()


class AuthenticatedAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='banker@freedombankva.com', email='banker@freedombankva.com', password='Freedom2026!')
        self.client.force_authenticate(user=self.user)


class ValidationTests(AuthenticatedAPITestCase):
    VALID = {
        'borrowerName': 'Priya Sharma',
        'phone': '7035551234',
        'email': 'priya@meridianlogistics.com',
        'companyName': 'Meridian Logistics LLC',
    }

    def test_all_valid_fields_pass(self):
        res = self.client.post(VALIDATE_URL, self.VALID, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for field in ('borrowerName', 'phone', 'email', 'companyName'):
            self.assertTrue(res.data[field]['ok'], f'{field} should be ok')

    def test_phone_with_too_few_digits_rejected(self):
        res = self.client.post(VALIDATE_URL, {**self.VALID, 'phone': '703-55-019'}, format='json')
        self.assertFalse(res.data['phone']['ok'])

    def test_phone_formatting_characters_ignored(self):
        """(703) 555-1234 should validate the same as 7035551234."""
        res = self.client.post(VALIDATE_URL, {**self.VALID, 'phone': '(703) 555-1234'}, format='json')
        self.assertTrue(res.data['phone']['ok'])

    def test_phone_with_too_many_digits_rejected(self):
        res = self.client.post(VALIDATE_URL, {**self.VALID, 'phone': '17035551234999'}, format='json')
        self.assertFalse(res.data['phone']['ok'])

    def test_email_missing_at_sign_rejected(self):
        res = self.client.post(VALIDATE_URL, {**self.VALID, 'email': 'priya.meridianlogistics.com'}, format='json')
        self.assertFalse(res.data['email']['ok'])

    def test_email_missing_domain_dot_rejected(self):
        res = self.client.post(VALIDATE_URL, {**self.VALID, 'email': 'priya@meridianlogistics'}, format='json')
        self.assertFalse(res.data['email']['ok'])

    def test_blank_borrower_name_rejected(self):
        res = self.client.post(VALIDATE_URL, {**self.VALID, 'borrowerName': '  '}, format='json')
        self.assertFalse(res.data['borrowerName']['ok'])

    def test_blank_company_name_rejected(self):
        res = self.client.post(VALIDATE_URL, {**self.VALID, 'companyName': ''}, format='json')
        self.assertFalse(res.data['companyName']['ok'])

    def test_validate_requires_authentication(self):
        self.client.force_authenticate(user=None)
        res = self.client.post(VALIDATE_URL, self.VALID, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class CreateRequestTests(AuthenticatedAPITestCase):
    VALID = {
        'borrowerName': 'Priya Sharma',
        'phone': '7035551234',
        'email': 'priya@meridianlogistics.com',
        'companyName': 'Meridian Logistics LLC',
    }

    def test_send_with_all_valid_fields_creates_sent_request(self):
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['status'], 'sent')
        self.assertIsNotNone(res.data['linkExpiresAt'])

    def test_send_generates_a_unique_link_token(self):
        r1 = self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json').data
        r2 = self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json').data
        t1 = DocumentRequest.objects.get(id=r1['id']).link_token
        t2 = DocumentRequest.objects.get(id=r2['id']).link_token
        self.assertNotEqual(t1, t2)

    def test_send_rejects_invalid_phone_server_side(self):
        """Client-side validation is not trusted -- server re-checks on send."""
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'phone': '123', 'action': 'send'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DocumentRequest.objects.filter(phone='123').exists())

    def test_send_rejects_invalid_email_server_side(self):
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'email': 'not-an-email', 'action': 'send'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_draft_does_not_require_valid_phone_or_email(self):
        res = self.client.post(LIST_CREATE_URL, {
            'borrowerName': 'Priya Sharma', 'phone': '', 'email': '', 'companyName': '', 'action': 'draft',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['status'], 'draft')

    def test_draft_requires_at_least_a_borrower_name(self):
        res = self.client.post(LIST_CREATE_URL, {'borrowerName': '', 'action': 'draft'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_draft_has_no_link_token(self):
        res = self.client.post(LIST_CREATE_URL, {'borrowerName': 'Priya Sharma', 'action': 'draft'}, format='json')
        self.assertIsNone(res.data['linkExpiresAt'])

    def test_list_requires_authentication(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(LIST_CREATE_URL)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class MetricsTests(AuthenticatedAPITestCase):
    def test_active_requests_counts_only_sent_status(self):
        DocumentRequest.objects.create(borrower_name='A', status='sent', created_by=self.user)
        DocumentRequest.objects.create(borrower_name='B', status='sent', created_by=self.user)
        DocumentRequest.objects.create(borrower_name='C', status='draft', created_by=self.user)
        DocumentRequest.objects.create(borrower_name='D', status='expired', created_by=self.user)

        res = self.client.get(LIST_CREATE_URL)
        self.assertEqual(res.data['metrics']['activeRequests'], 2)

    def test_parking_bay_and_fraud_metrics_are_now_real(self):
        """Step 4 exists now -- these are real counts, not the honest-null
        placeholder from before Step 4 was built."""
        sent = self.client.post(LIST_CREATE_URL, {
            'borrowerName': 'Priya Sharma', 'phone': '7035551234',
            'email': 'priya@meridianlogistics.com', 'companyName': 'Meridian Logistics LLC',
            'action': 'send',
        }, format='json').data
        doc_request = DocumentRequest.objects.get(id=sent['id'])
        item = doc_request.checklist_items.first()
        self.client.post(f'/api/upload/{doc_request.link_token}/documents',
                          {'checklistItemId': item.id, 'file': SimpleUploadedFile('a.txt', b'x')}, format='multipart')

        res = self.client.get(LIST_CREATE_URL)
        self.assertEqual(res.data['metrics']['docsInParkingBay'], 1)
        self.assertEqual(res.data['metrics']['sessionsEndedFraud'], 0)

    def test_awaiting_customer_excludes_requests_with_any_upload(self):
        r1 = self.client.post(LIST_CREATE_URL, {
            'borrowerName': 'Priya Sharma', 'phone': '7035551234',
            'email': 'priya@meridianlogistics.com', 'companyName': 'Meridian Logistics LLC',
            'action': 'send',
        }, format='json').data
        self.client.post(LIST_CREATE_URL, {
            'borrowerName': 'Marcus Lee', 'phone': '7035559999',
            'email': 'marcus@harborpoint.com', 'companyName': 'Harbor Point Dental PC',
            'action': 'send',
        }, format='json')

        doc_request = DocumentRequest.objects.get(id=r1['id'])
        item = doc_request.checklist_items.first()
        self.client.post(f'/api/upload/{doc_request.link_token}/documents',
                          {'checklistItemId': item.id, 'file': SimpleUploadedFile('a.txt', b'x')}, format='multipart')

        res = self.client.get(LIST_CREATE_URL)
        # 2 sent total, 1 has an upload already -> only 1 still "awaiting customer"
        self.assertEqual(res.data['metrics']['activeRequests'], 2)
        self.assertEqual(res.data['metrics']['awaitingCustomer'], 1)

    def test_list_includes_all_requests_regardless_of_status(self):
        DocumentRequest.objects.create(borrower_name='A', status='draft', created_by=self.user)
        DocumentRequest.objects.create(borrower_name='B', status='sent', created_by=self.user)
        res = self.client.get(LIST_CREATE_URL)
        self.assertEqual(len(res.data['requests']), 2)

    def test_stat_strip_metrics_are_null_not_fake_zero_when_nothing_exists_yet(self):
        res = self.client.get(LIST_CREATE_URL)
        self.assertEqual(res.data['metrics']['twinsCreatedThisMonth'], 0)  # real count, legitimately 0
        self.assertIsNone(res.data['metrics']['pctValuesAutoVerified'])  # no values extracted anywhere yet
        self.assertIsNone(res.data['metrics']['avgRequestToExtractionDays'])  # nothing has reached extraction yet

    def test_loans_by_stage_counts_only_the_two_real_stages(self):
        _make_sent_request(self.client, self.user)  # sent, not yet queued -> "documents"
        res = self.client.get(LIST_CREATE_URL)
        self.assertEqual(res.data['metrics']['loansByStage'], {'documents': 1, 'extraction': 0})


class ResendTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.expired = DocumentRequest.objects.create(
            borrower_name='Elena Ortiz', company_name='Blue Ridge Catering Co.',
            status='expired', created_by=self.user,
        )

    def test_resend_on_expired_request_reissues_link_and_sets_sent(self):
        res = self.client.post(f'/api/requests/{self.expired.id}/resend')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'sent')
        self.assertIsNotNone(res.data['linkExpiresAt'])

    def test_resend_generates_a_new_token_different_from_before(self):
        self.expired.link_token = 'old-token-123'
        self.expired.save(update_fields=['link_token'])
        self.client.post(f'/api/requests/{self.expired.id}/resend')
        self.expired.refresh_from_db()
        self.assertNotEqual(self.expired.link_token, 'old-token-123')

    def test_resend_blocked_once_uploads_are_complete(self):
        completed = DocumentRequest.objects.create(borrower_name='Marcus Lee', status='uploads_complete', created_by=self.user)
        res = self.client.post(f'/api/requests/{completed.id}/resend')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resend_on_nonexistent_request_404s(self):
        res = self.client.post('/api/requests/999999/resend')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class RequestEmailTests(AuthenticatedAPITestCase):
    """Step 3 -- no real mail provider exists, so 'sending' means composing
    the content and logging it (RequestEmail row), not actually delivering it."""

    VALID = {
        'borrowerName': 'Priya Sharma',
        'phone': '7035551234',
        'email': 'priya@meridianlogistics.com',
        'companyName': 'Meridian Logistics LLC',
        'selectedItems': TEST_CHECKLIST_SELECTION,
    }

    def test_sending_a_request_logs_exactly_one_email(self):
        self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        self.assertEqual(RequestEmail.objects.count(), 1)

    def test_draft_does_not_log_an_email(self):
        self.client.post(LIST_CREATE_URL, {'borrowerName': 'Priya Sharma', 'action': 'draft'}, format='json')
        self.assertEqual(RequestEmail.objects.count(), 0)

    def test_logged_email_goes_to_the_applicants_address(self):
        self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        email = RequestEmail.objects.get()
        self.assertEqual(email.to_email, self.VALID['email'])
        self.assertEqual(email.from_email, 'requests@freedombankva.com')

    def test_logged_email_subject_matches_mockup_copy(self):
        self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        email = RequestEmail.objects.get()
        self.assertEqual(email.subject, 'Documents needed to begin your loan application')

    def test_logged_email_body_includes_every_checklist_item(self):
        self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        email = RequestEmail.objects.get()
        for name in TEST_CHECKLIST_NAMES:
            self.assertIn(name, email.body_text)

    def test_default_selection_email_includes_only_lender_items(self):
        """No selectedItems provided -> falls back to the real default
        selection -- the email must still only ever list Lender items,
        never the internal-only Loan Admin ones."""
        self.client.post(LIST_CREATE_URL, {**self.VALID, 'selectedItems': None, 'action': 'send'}, format='json')
        email = RequestEmail.objects.get()
        for category, name, audience in checklist_module.default_selection():
            if audience == 'lender':
                self.assertIn(name, email.body_text)
            else:
                self.assertNotIn(name, email.body_text)

    def test_logged_email_includes_anti_phishing_footer(self):
        self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        email = RequestEmail.objects.get()
        self.assertIn('Freedom Bank will never ask for your password or one-time codes by email', email.body_text)

    def test_logged_email_expiry_date_matches_link_expires_at(self):
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        doc_request = DocumentRequest.objects.get(id=res.data['id'])
        email = RequestEmail.objects.get()
        self.assertIn(doc_request.link_expires_at.strftime('%b %d, %Y'), email.body_text)

    def test_logged_email_body_includes_borrower_and_company_name(self):
        self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        email = RequestEmail.objects.get()
        self.assertIn('Priya Sharma', email.body_text)
        self.assertIn('Meridian Logistics LLC', email.body_text)

    def test_logged_email_body_includes_the_upload_link_token(self):
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        doc_request = DocumentRequest.objects.get(id=res.data['id'])
        email = RequestEmail.objects.get()
        self.assertIn(doc_request.link_token, email.body_text)

    def test_resend_logs_a_second_email(self):
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        self.client.post(f'/api/requests/{res.data["id"]}/resend')
        self.assertEqual(RequestEmail.objects.filter(document_request_id=res.data['id']).count(), 2)

    def test_get_latest_email_returns_the_most_recent_one(self):
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        request_id = res.data['id']
        self.client.post(f'/api/requests/{request_id}/resend')  # logs a 2nd email with a new token

        email_res = self.client.get(f'/api/requests/{request_id}/email')
        self.assertEqual(email_res.status_code, status.HTTP_200_OK)
        doc_request = DocumentRequest.objects.get(id=request_id)
        self.assertIn(doc_request.link_token, email_res.data['bodyText'])

    def test_get_email_404s_when_none_logged_yet(self):
        draft = DocumentRequest.objects.create(borrower_name='Nobody Yet', status='draft', created_by=self.user)
        res = self.client.get(f'/api/requests/{draft.id}/email')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_email_requires_authentication(self):
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'action': 'send'}, format='json')
        self.client.force_authenticate(user=None)
        email_res = self.client.get(f'/api/requests/{res.data["id"]}/email')
        self.assertEqual(email_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_request_email_is_read_only_via_admin(self):
        from django.contrib import admin
        model_admin = admin.site._registry[RequestEmail]
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_change_permission(None))


def _make_sent_request(client, user, **overrides):
    payload = {
        'borrowerName': 'Priya Sharma', 'phone': '7035551234',
        'email': 'priya@meridianlogistics.com', 'companyName': 'Meridian Logistics LLC',
        'action': 'send', 'selectedItems': TEST_CHECKLIST_SELECTION,
    }
    payload.update(overrides)
    res = client.post(LIST_CREATE_URL, payload, format='json')
    return DocumentRequest.objects.get(id=res.data['id'])


class UploadPortalTests(APITestCase):
    """Step 4 -- public (no-auth) upload portal. Uses a plain APITestCase,
    not AuthenticatedAPITestCase: the whole point is these endpoints work
    without a session."""

    def setUp(self):
        self.banker = User.objects.create_user(username='banker@freedombankva.com', email='banker@freedombankva.com', password='Freedom2026!')
        self.client.force_authenticate(user=self.banker)
        self.doc_request = _make_sent_request(self.client, self.banker)
        self.client.force_authenticate(user=None)  # everything below is anonymous

    def test_checklist_items_created_at_send_time(self):
        self.assertEqual(self.doc_request.checklist_items.count(), len(TEST_CHECKLIST_SELECTION))
        names = list(self.doc_request.checklist_items.order_by('order').values_list('name', flat=True))
        self.assertEqual(names, TEST_CHECKLIST_NAMES)

    def test_info_endpoint_returns_checklist_and_starts_session_timer(self):
        res = self.client.get(f'/api/upload/{self.doc_request.link_token}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['items']), len(TEST_CHECKLIST_SELECTION))
        self.assertTrue(all(i['status'] == 'pending' for i in res.data['items']))
        self.assertIsNotNone(res.data['sessionSecondsRemaining'])
        self.assertTrue(UploadSession.objects.get(document_request=self.doc_request).started_at is not None)

    def test_info_endpoint_invalid_token_returns_410(self):
        res = self.client.get('/api/upload/not-a-real-token')
        self.assertEqual(res.status_code, status.HTTP_410_GONE)

    def test_upload_success_marks_item_uploaded(self):
        item = self.doc_request.checklist_items.first()
        res = self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('statement.pdf', b'%PDF-1.4 fake content'),
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        item.refresh_from_db()
        self.assertEqual(item.status, 'uploaded')
        self.assertIsNotNone(item.current_file)

    def test_upload_writes_file_to_disk(self):
        from django.conf import settings
        from . import storage

        item = self.doc_request.checklist_items.first()
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('statement.pdf', b'hello from disk'),
        }, format='multipart')
        item.refresh_from_db()
        abs_path = storage.absolute_path(item.current_file.file_path)
        self.assertTrue(os.path.exists(abs_path))
        with open(abs_path, 'rb') as f:
            self.assertEqual(f.read(), b'hello from disk')

    def test_upload_missing_checklist_item_is_a_failed_attempt(self):
        res = self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'file': SimpleUploadedFile('x.pdf', b'x'),
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        session = UploadSession.objects.get(document_request=self.doc_request)
        self.assertEqual(session.failed_attempts, 1)

    def test_upload_missing_file_is_a_failed_attempt(self):
        item = self.doc_request.checklist_items.first()
        res = self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id,
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_oversized_file_rejected(self):
        from . import views as v
        # Temporarily lower the cap instead of actually allocating/sending a
        # 20MB+ body in a test -- .size can't just be overridden on the
        # SimpleUploadedFile since the test client re-serializes it through
        # real multipart encoding, so the server sees the true byte count.
        original_limit = v.MAX_FILE_SIZE_BYTES
        v.MAX_FILE_SIZE_BYTES = 5
        self.addCleanup(setattr, v, 'MAX_FILE_SIZE_BYTES', original_limit)

        item = self.doc_request.checklist_items.first()
        big = SimpleUploadedFile('big.pdf', b'x' * 10)  # 10 bytes > the 5-byte test cap
        res = self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': big,
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reupload_replaces_current_file_keeps_old_row(self):
        item = self.doc_request.checklist_items.first()
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('v1.pdf', b'version one'),
        }, format='multipart')
        first_file_id = ChecklistItem.objects.get(id=item.id).current_file_id

        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('v2.pdf', b'version two'),
        }, format='multipart')
        item.refresh_from_db()

        self.assertNotEqual(item.current_file_id, first_file_id)
        self.assertEqual(UploadedFile.objects.filter(checklist_item=item).count(), 2)  # old row preserved

    def test_all_items_uploaded_marks_request_uploads_complete(self):
        for item in self.doc_request.checklist_items.all():
            self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
                'checklistItemId': item.id, 'file': SimpleUploadedFile(f'{item.id}.pdf', b'content'),
            }, format='multipart')
        self.doc_request.refresh_from_db()
        self.assertEqual(self.doc_request.status, 'uploads_complete')

    def test_partial_upload_keeps_request_sent(self):
        item = self.doc_request.checklist_items.first()
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('a.pdf', b'x'),
        }, format='multipart')
        self.doc_request.refresh_from_db()
        self.assertEqual(self.doc_request.status, 'sent')

    def test_session_expiry_blocks_further_upload(self):
        from datetime import timedelta
        from django.utils import timezone

        self.client.get(f'/api/upload/{self.doc_request.link_token}')  # starts the session
        session = UploadSession.objects.get(document_request=self.doc_request)
        session.started_at = timezone.now() - timedelta(minutes=25)  # older than the 20-min window
        session.save(update_fields=['started_at'])

        item = self.doc_request.checklist_items.first()
        res = self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('late.pdf', b'x'),
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_410_GONE)
        item.refresh_from_db()
        self.assertEqual(item.status, 'pending')  # rejected, nothing saved

    def test_expired_link_blocks_upload_and_flips_status(self):
        from datetime import timedelta
        from django.utils import timezone

        self.doc_request.link_expires_at = timezone.now() - timedelta(days=1)
        self.doc_request.save(update_fields=['link_expires_at'])

        res = self.client.get(f'/api/upload/{self.doc_request.link_token}')
        self.assertEqual(res.status_code, status.HTTP_410_GONE)
        self.doc_request.refresh_from_db()
        self.assertEqual(self.doc_request.status, 'expired')

    def test_repeated_failed_uploads_trip_fraud_guard(self):
        # 5 failed attempts (missing file) trips the guard
        for _ in range(5):
            self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {}, format='multipart')
        self.doc_request.refresh_from_db()
        self.assertEqual(self.doc_request.status, 'fraud_stopped')
        session = UploadSession.objects.get(document_request=self.doc_request)
        self.assertEqual(session.fraud_reason, 'Repeated failed upload attempts')

    def test_fraud_trip_preserves_already_uploaded_files(self):
        items = list(self.doc_request.checklist_items.all())
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': items[0].id, 'file': SimpleUploadedFile('a.pdf', b'keep me'),
        }, format='multipart')
        # then trip fraud via failed attempts
        for _ in range(5):
            self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {}, format='multipart')

        items[0].refresh_from_db()
        self.assertEqual(items[0].status, 'uploaded')
        self.assertIsNotNone(items[0].current_file)

    def test_fraud_trip_blocks_further_uploads(self):
        for _ in range(5):
            self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {}, format='multipart')

        item = self.doc_request.checklist_items.first()
        res = self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('too-late.pdf', b'x'),
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_410_GONE)

    def test_fraud_trip_logs_an_alert_email_to_the_banker(self):
        for _ in range(5):
            self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {}, format='multipart')

        alert = RequestEmail.objects.get(document_request=self.doc_request, kind='fraud_alert')
        self.assertEqual(alert.to_email, self.banker.email)
        self.assertIn('Repeated failed upload attempts', alert.body_text)

    def test_high_volume_of_attempts_trips_fraud_as_automated_activity(self):
        item = self.doc_request.checklist_items.first()
        # 20 successful-looking attempts (re-uploads to the same item) --
        # volume-based heuristic, distinct from the failed-attempts one.
        for i in range(20):
            self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
                'checklistItemId': item.id, 'file': SimpleUploadedFile(f'{i}.pdf', b'x'),
            }, format='multipart')
        self.doc_request.refresh_from_db()
        self.assertEqual(self.doc_request.status, 'fraud_stopped')
        session = UploadSession.objects.get(document_request=self.doc_request)
        self.assertIn('automated', session.fraud_reason.lower())

    def test_resend_resets_session_but_keeps_checklist_progress(self):
        item = self.doc_request.checklist_items.first()
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('a.pdf', b'x'),
        }, format='multipart')
        self.assertTrue(UploadSession.objects.filter(document_request=self.doc_request).exists())

        self.client.force_authenticate(user=self.banker)
        self.client.post(f'/api/requests/{self.doc_request.id}/resend')
        self.client.force_authenticate(user=None)

        self.assertFalse(UploadSession.objects.filter(document_request=self.doc_request).exists())
        item.refresh_from_db()
        self.assertEqual(item.status, 'uploaded')  # progress kept


class ReferenceNumberAndConfirmationEmailTests(APITestCase):
    """Step 5 -- the customer-facing reference number and the completion
    confirmation email that fires once all checklist items are uploaded."""

    def setUp(self):
        self.banker = User.objects.create_user(username='banker@freedombankva.com', email='banker@freedombankva.com', password='Freedom2026!')
        self.client.force_authenticate(user=self.banker)

    def test_reference_number_assigned_on_send(self):
        doc_request = _make_sent_request(self.client, self.banker)
        self.assertIsNotNone(doc_request.reference_number)
        self.assertEqual(doc_request.reference_number, f'REQ-{doc_request.created_at.year}-{doc_request.id:04d}')

    def test_draft_has_no_reference_number(self):
        res = self.client.post(LIST_CREATE_URL, {'borrowerName': 'Priya Sharma', 'action': 'draft'}, format='json')
        self.assertIsNone(res.data['referenceNumber'])

    def test_reference_number_stable_across_resend(self):
        doc_request = _make_sent_request(self.client, self.banker)
        original = doc_request.reference_number
        self.client.post(f'/api/requests/{doc_request.id}/resend')
        doc_request.refresh_from_db()
        self.assertEqual(doc_request.reference_number, original)

    def test_reference_number_unique_per_request(self):
        r1 = _make_sent_request(self.client, self.banker)
        r2 = _make_sent_request(self.client, self.banker)
        self.assertNotEqual(r1.reference_number, r2.reference_number)

    def test_reference_number_included_in_list_response(self):
        doc_request = _make_sent_request(self.client, self.banker)
        res = self.client.get(LIST_CREATE_URL)
        row = next(r for r in res.data['requests'] if r['id'] == doc_request.id)
        self.assertEqual(row['referenceNumber'], doc_request.reference_number)

    def test_reference_number_included_in_upload_info(self):
        doc_request = _make_sent_request(self.client, self.banker)
        self.client.force_authenticate(user=None)
        res = self.client.get(f'/api/upload/{doc_request.link_token}')
        self.assertEqual(res.data['referenceNumber'], doc_request.reference_number)

    def test_completion_logs_confirmation_email_exactly_once(self):
        doc_request = _make_sent_request(self.client, self.banker)
        self.client.force_authenticate(user=None)
        for item in doc_request.checklist_items.all():
            self.client.post(f'/api/upload/{doc_request.link_token}/documents', {
                'checklistItemId': item.id, 'file': SimpleUploadedFile(f'{item.id}.pdf', b'content'),
            }, format='multipart')

        self.assertEqual(RequestEmail.objects.filter(document_request=doc_request, kind='confirmation').count(), 1)

    def test_confirmation_email_not_logged_on_partial_upload(self):
        doc_request = _make_sent_request(self.client, self.banker)
        self.client.force_authenticate(user=None)
        item = doc_request.checklist_items.first()
        self.client.post(f'/api/upload/{doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('a.pdf', b'x'),
        }, format='multipart')

        self.assertEqual(RequestEmail.objects.filter(document_request=doc_request, kind='confirmation').count(), 0)

    def test_confirmation_email_addressed_to_borrower_with_reference(self):
        doc_request = _make_sent_request(self.client, self.banker)
        self.client.force_authenticate(user=None)
        for item in doc_request.checklist_items.all():
            self.client.post(f'/api/upload/{doc_request.link_token}/documents', {
                'checklistItemId': item.id, 'file': SimpleUploadedFile(f'{item.id}.pdf', b'content'),
            }, format='multipart')

        doc_request.refresh_from_db()
        email = RequestEmail.objects.get(document_request=doc_request, kind='confirmation')
        self.assertEqual(email.to_email, doc_request.email)
        self.assertIn(doc_request.reference_number, email.body_text)
        self.assertIn('Your documents have been received', email.subject)

    def test_confirmation_email_not_relogged_on_reupload_after_completion(self):
        doc_request = _make_sent_request(self.client, self.banker)
        self.client.force_authenticate(user=None)
        items = list(doc_request.checklist_items.all())
        for item in items:
            self.client.post(f'/api/upload/{doc_request.link_token}/documents', {
                'checklistItemId': item.id, 'file': SimpleUploadedFile(f'{item.id}.pdf', b'content'),
            }, format='multipart')

        # re-upload to an already-uploaded item after completion -- must not fire a 2nd confirmation
        self.client.post(f'/api/upload/{doc_request.link_token}/documents', {
            'checklistItemId': items[0].id, 'file': SimpleUploadedFile('replacement.pdf', b'new content'),
        }, format='multipart')

        self.assertEqual(RequestEmail.objects.filter(document_request=doc_request, kind='confirmation').count(), 1)


class BankerFileAccessTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.doc_request = _make_sent_request(self.client, self.user)
        item = self.doc_request.checklist_items.first()
        self.client.force_authenticate(user=None)
        upload_res = self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('statement.pdf', b'bank statement contents'),
        }, format='multipart')
        self.upload_id = upload_res.data['id']
        self.client.force_authenticate(user=self.user)

    def test_list_uploaded_files_requires_auth(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(f'/api/requests/{self.doc_request.id}/uploads')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_uploaded_files_shows_the_upload(self):
        res = self.client.get(f'/api/requests/{self.doc_request.id}/uploads')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['fileName'], 'statement.pdf')

    def test_serve_uploaded_file_returns_original_bytes(self):
        res = self.client.get(f'/api/requests/{self.doc_request.id}/uploads/{self.upload_id}/serve')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.content, b'bank statement contents')

    def test_serve_nonexistent_file_404s(self):
        res = self.client.get(f'/api/requests/{self.doc_request.id}/uploads/999999/serve')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class ParkingBayReviewTests(AuthenticatedAPITestCase):
    """Step 6 -- banker opens each parked file, approves or flags it, and two
    batch actions (bundled flags email, extraction kick-start) unlock once
    every uploaded document has a decision."""

    def setUp(self):
        super().setUp()
        self.doc_request = _make_sent_request(self.client, self.user)
        self.items = list(self.doc_request.checklist_items.order_by('order').all())
        self.client.force_authenticate(user=None)
        for item in self.items:
            self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
                'checklistItemId': item.id, 'file': SimpleUploadedFile(f'{item.id}.pdf', b'content'),
            }, format='multipart')
        self.client.force_authenticate(user=self.user)
        self.items = list(self.doc_request.checklist_items.order_by('order').all())  # refresh: current_file now set

    def _review(self, item_id, decision, comment=''):
        return self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/{item_id}/review', {
            'decision': decision, 'comment': comment,
        }, format='json')

    def test_parking_bay_lists_exactly_the_uploaded_files(self):
        res = self.client.get(f'/api/requests/{self.doc_request.id}/parking-bay')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['items']), len(TEST_CHECKLIST_SELECTION))
        self.assertTrue(all(i['file'] is not None for i in res.data['items']))
        self.assertTrue(all(i['file']['reviewStatus'] == 'pending' for i in res.data['items']))

    def test_parking_bay_requires_auth(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(f'/api/requests/{self.doc_request.id}/parking-bay')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_parking_bay_404s_for_nonexistent_request(self):
        res = self.client.get('/api/requests/999999/parking-bay')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_approve_marks_ready_for_extraction(self):
        res = self._review(self.items[0].id, 'approve')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['file']['reviewStatus'], 'approved')

    def test_flag_without_comment_is_rejected(self):
        res = self._review(self.items[0].id, 'flag')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.items[0].current_file.refresh_from_db()
        self.assertEqual(self.items[0].current_file.review_status, 'pending')

    def test_flag_with_comment_is_recorded(self):
        res = self._review(self.items[0].id, 'flag', comment='Lease dated 2019 -- need a document from the last 90 days.')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['file']['reviewStatus'], 'flagged')
        self.assertIn('2019', res.data['file']['reviewComment'])

    def test_review_requires_a_valid_decision(self):
        res = self._review(self.items[0].id, 'maybe')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_review_an_item_with_no_upload(self):
        empty_item = ChecklistItem.objects.create(document_request=self.doc_request, name='Extra item', order=99)
        res = self._review(empty_item.id, 'approve')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_summary_reflects_live_decisions(self):
        self._review(self.items[0].id, 'approve')
        self._review(self.items[1].id, 'flag', comment='needs redo')
        res = self.client.get(f'/api/requests/{self.doc_request.id}/parking-bay')
        self.assertEqual(res.data['approvedCount'], 1)
        self.assertEqual(res.data['flaggedCount'], 1)
        self.assertFalse(res.data['reviewComplete'])  # 3 of 5 still pending

    def test_review_complete_once_every_item_has_a_decision(self):
        for item in self.items:
            self._review(item.id, 'approve')
        res = self.client.get(f'/api/requests/{self.doc_request.id}/parking-bay')
        self.assertTrue(res.data['reviewComplete'])
        self.assertEqual(res.data['approvedCount'], len(self.items))

    def test_submit_for_extraction_does_not_send_any_email(self):
        self._review(self.items[0].id, 'approve')
        self.assertEqual(RequestEmail.objects.filter(document_request=self.doc_request, kind='review_flags').count(), 0)

    def test_send_flags_email_requires_at_least_one_flag(self):
        res = self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/send-flags-email')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_flags_email_bundles_all_flags_into_one_email(self):
        self._review(self.items[0].id, 'flag', comment='Bad statement')
        self._review(self.items[1].id, 'flag', comment='Wrong tax year')
        res = self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/send-flags-email')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['flaggedCount'], 2)

        emails = RequestEmail.objects.filter(document_request=self.doc_request, kind='review_flags')
        self.assertEqual(emails.count(), 1)  # one bundled email, not one per flag
        body = emails.get().body_text
        self.assertIn('Bad statement', body)
        self.assertIn('Wrong tax year', body)
        self.assertEqual(emails.get().to_email, self.doc_request.email)

    def test_kick_start_blocked_until_review_complete(self):
        self._review(self.items[0].id, 'approve')  # only 1 of 5 reviewed
        res = self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/kick-start-extraction')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.doc_request.refresh_from_db()
        self.assertIsNone(self.doc_request.extraction_queued_at)

    def test_kick_start_queues_only_approved_files(self):
        for item in self.items[:-1]:
            self._review(item.id, 'approve')
        self._review(self.items[-1].id, 'flag', comment='needs redo')

        res = self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/kick-start-extraction')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['queuedCount'], len(self.items) - 1)  # flagged one excluded
        self.doc_request.refresh_from_db()
        self.assertIsNotNone(self.doc_request.extraction_queued_at)

    def test_kick_start_cannot_be_queued_twice(self):
        for item in self.items:
            self._review(item.id, 'approve')
        self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/kick-start-extraction')
        res = self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/kick-start-extraction')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_flagged_document_re_enters_parking_bay_on_reupload(self):
        item = self.items[0]
        self._review(item.id, 'flag', comment='needs redo')
        old_file_id = item.current_file_id

        self.client.force_authenticate(user=None)
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('replacement.pdf', b'fixed content'),
        }, format='multipart')
        self.client.force_authenticate(user=self.user)

        item.refresh_from_db()
        self.assertNotEqual(item.current_file_id, old_file_id)
        self.assertEqual(item.current_file.review_status, 'pending')  # back in the parking bay for review

        old_file = UploadedFile.objects.get(id=old_file_id)
        self.assertEqual(old_file.review_status, 'flagged')  # old flagged history preserved
        self.assertEqual(old_file.review_comment, 'needs redo')

    def test_dashboard_list_flags_a_request_with_a_flagged_item(self):
        """`status` alone (e.g. 'uploads_complete') can't show a flag -- the
        dashboard needs a separate signal since every Lender item can have a
        file while one of those files is still flagged for re-upload."""
        res = self.client.get(LIST_CREATE_URL)
        row = next(r for r in res.data['requests'] if r['id'] == self.doc_request.id)
        self.assertFalse(row['hasFlaggedItems'])

        self._review(self.items[0].id, 'flag', comment='needs redo')
        res = self.client.get(LIST_CREATE_URL)
        row = next(r for r in res.data['requests'] if r['id'] == self.doc_request.id)
        self.assertTrue(row['hasFlaggedItems'])

    def test_dashboard_flag_clears_once_the_item_is_reuploaded(self):
        item = self.items[0]
        self._review(item.id, 'flag', comment='needs redo')

        self.client.force_authenticate(user=None)
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('replacement.pdf', b'fixed content'),
        }, format='multipart')
        self.client.force_authenticate(user=self.user)

        res = self.client.get(LIST_CREATE_URL)
        row = next(r for r in res.data['requests'] if r['id'] == self.doc_request.id)
        self.assertFalse(row['hasFlaggedItems'])  # superseded by the fresh (pending) upload


class TwinExtractionTests(AuthenticatedAPITestCase):
    """Step 7 -- a real, DB-backed stage machine for the document twin and
    the shared business twin. No real OCR/AI pipeline exists (explicit scope
    decision): classification is a deterministic lookup by checklist item
    name, and Extracted/Provenance/Confidence complete with honest
    placeholder detail rather than fabricated values."""

    def setUp(self):
        super().setUp()
        self.doc_request = _make_sent_request(self.client, self.user)
        items = list(self.doc_request.checklist_items.order_by('order').all())
        self.client.force_authenticate(user=None)
        for item in items:
            self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
                'checklistItemId': item.id, 'file': SimpleUploadedFile(f'{item.id}.pdf', b'content'),
            }, format='multipart')
        self.client.force_authenticate(user=self.user)
        items = list(self.doc_request.checklist_items.order_by('order').all())

        for item in items[:-1]:
            self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/{item.id}/review', {
                'decision': 'approve',
            }, format='json')
        self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/{items[-1].id}/review', {
            'decision': 'flag', 'comment': 'needs redo',
        }, format='json')

        self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/kick-start-extraction')
        self.items = items

    def _advance_twin(self, twin_id):
        return self.client.post(f'/api/requests/{self.doc_request.id}/extraction/{twin_id}/advance')

    def _advance_business_twin(self):
        return self.client.post(f'/api/requests/{self.doc_request.id}/business-twin/advance')

    def test_kick_start_creates_a_twin_per_approved_file_only(self):
        self.assertEqual(DocumentTwin.objects.filter(document_request=self.doc_request).count(), len(self.items) - 1)  # not the flagged one
        self.assertTrue(BusinessTwin.objects.filter(document_request=self.doc_request).exists())

    def test_twins_start_at_their_first_stage(self):
        res = self.client.get(f'/api/requests/{self.doc_request.id}/extraction')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['documentTwins']), len(self.items) - 1)
        self.assertTrue(all(t['currentStage'] == 'received' for t in res.data['documentTwins']))
        self.assertEqual(res.data['businessTwin']['currentStage'], 'relationship')

    def test_extraction_view_400s_before_kickoff(self):
        never_queued = _make_sent_request(self.client, self.user)
        res = self.client.get(f'/api/requests/{never_queued.id}/extraction')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_document_twin_stage_sequence_enforced(self):
        twin = DocumentTwin.objects.filter(document_request=self.doc_request).first()
        expected = ['classified', 'extracted', 'provenance', 'confidence']
        for stage in expected:
            res = self._advance_twin(twin.id)
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertEqual(res.data['currentStage'], stage)

        # already at the final stage -- can't advance further
        res = self._advance_twin(twin.id)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_classification_label_derived_from_checklist_item_name(self):
        # self.items[0] is TEST_CHECKLIST_SELECTION[0] -- "Corporate Resolution"
        twin = DocumentTwin.objects.get(document_request=self.doc_request, uploaded_file=self.items[0].current_file)
        res = self._advance_twin(twin.id)
        self.assertEqual(res.data['classificationLabel'], 'Corporate resolution')

    def test_advance_nonexistent_twin_404s(self):
        res = self._advance_twin(999999)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_overall_percent_is_a_real_aggregate(self):
        twin = DocumentTwin.objects.filter(document_request=self.doc_request).first()
        self._advance_twin(twin.id)  # document twin: 2 of 5 stages -> 40%
        self._advance_business_twin()  # business twin: 2 of 5 stages -> 40%
        res = self._advance_twin(twin.id)  # document twin: 3 of 5 -> 60%
        # overall = average(document 60%, business 40%) = 50%
        self.assertEqual(res.data['overallPercent'], 50)

    def test_every_stage_transition_writes_audit_events(self):
        twin = DocumentTwin.objects.filter(document_request=self.doc_request).first()
        self._advance_twin(twin.id)
        events = list(ExtractionEvent.objects.filter(document_request=self.doc_request, document_twin=twin).order_by('created_at'))
        # kick-start already logged document_twin.received; advancing to
        # 'classified' adds exactly one stage event + one matching audit.write.
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].event_type, 'document_twin.received')
        self.assertEqual(events[1].event_type, 'document_twin.classified')
        self.assertEqual(events[2].event_type, 'audit.write')

    def test_log_entries_in_chronological_order(self):
        twin = DocumentTwin.objects.filter(document_request=self.doc_request).first()
        self._advance_twin(twin.id)
        self._advance_twin(twin.id)
        res = self.client.get(f'/api/requests/{self.doc_request.id}/extraction')
        timestamps = [e['at'] for e in res.data['log']]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_business_twin_relationship_and_entities_start_immediately(self):
        res = self._advance_business_twin()  # relationship -> entities, no gate
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['currentStage'], 'entities')

    def test_business_twin_covenant_ledger_blocked_until_all_twins_extracted(self):
        self._advance_business_twin()  # -> entities
        res = self._advance_business_twin()  # -> covenant_ledger, but no twin has reached 'extracted' yet
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_business_twin_covenant_ledger_unlocks_once_all_twins_extracted(self):
        for twin in DocumentTwin.objects.filter(document_request=self.doc_request):
            self._advance_twin(twin.id)  # -> classified
            self._advance_twin(twin.id)  # -> extracted

        self._advance_business_twin()  # -> entities
        res = self._advance_business_twin()  # -> covenant_ledger
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['currentStage'], 'covenant_ledger')

    def test_business_twin_covenant_ledger_still_blocked_if_only_some_twins_extracted(self):
        twins = list(DocumentTwin.objects.filter(document_request=self.doc_request))
        self._advance_twin(twins[0].id)  # -> classified
        self._advance_twin(twins[0].id)  # -> extracted (only this one)

        self._advance_business_twin()  # -> entities
        res = self._advance_business_twin()  # -> covenant_ledger, blocked
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_business_twin_final_stage_cannot_advance_further(self):
        for twin in DocumentTwin.objects.filter(document_request=self.doc_request):
            self._advance_twin(twin.id)
            self._advance_twin(twin.id)
        for _ in range(4):  # relationship -> entities -> covenant_ledger -> indicators -> allocation
            self._advance_business_twin()
        res = self._advance_business_twin()
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_business_twin_advance_requires_extraction_kicked_off(self):
        never_queued = _make_sent_request(self.client, self.user)
        res = self.client.post(f'/api/requests/{never_queued.id}/business-twin/advance')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_concurrent_extractions_do_not_cross_contaminate(self):
        other = _make_sent_request(self.client, self.user)
        other_items = list(other.checklist_items.order_by('order').all())
        self.client.force_authenticate(user=None)
        for item in other_items:
            self.client.post(f'/api/upload/{other.link_token}/documents', {
                'checklistItemId': item.id, 'file': SimpleUploadedFile(f'other{item.id}.pdf', b'content'),
            }, format='multipart')
        self.client.force_authenticate(user=self.user)
        for item in other_items:
            self.client.post(f'/api/requests/{other.id}/parking-bay/{item.id}/review', {'decision': 'approve'}, format='json')
        self.client.post(f'/api/requests/{other.id}/parking-bay/kick-start-extraction')

        my_twin = DocumentTwin.objects.filter(document_request=self.doc_request).first()
        self._advance_twin(my_twin.id)  # advance only this request's twin

        other_twins = DocumentTwin.objects.filter(document_request=other)
        self.assertTrue(all(t.current_stage == 'received' for t in other_twins))  # untouched
        self.assertEqual(other_twins.count(), len(TEST_CHECKLIST_SELECTION))  # all approved there, independent of this request's twins


class ContentExtractionUnitTests(TestCase):
    """Direct tests of content_extraction.extract() -- real libraries, real
    bytes, real regex matches / real cell reads, no HTTP or DB involved."""

    def test_text_plain_dollar_amount(self):
        values = content_extraction.extract('text/plain', b'Total revenue: $4,218,400 this quarter')
        dollars = [v for v in values if v['fieldName'] == 'Dollar amount']
        self.assertEqual(len(dollars), 1)
        self.assertEqual(dollars[0]['value'], '$4,218,400')
        self.assertEqual(dollars[0]['source'], 'line 1')
        self.assertEqual(dollars[0]['confidence'], 0.95)

    def test_text_plain_percentage_and_ratio(self):
        values = content_extraction.extract('text/plain', b'DSCR 1.14x, confidence 98%')
        types = {v['fieldName'] for v in values}
        self.assertIn('Ratio', types)
        self.assertIn('Percentage', types)

    def test_text_plain_no_matches_returns_empty(self):
        self.assertEqual(content_extraction.extract('text/plain', b'nothing interesting here'), [])

    def test_unsupported_file_type_returns_empty_without_error(self):
        self.assertEqual(content_extraction.extract('application/zip', b'\x00\x01\x02'), [])

    def test_pdf_real_extraction(self):
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 720, 'Total revenue FY25: $4,218,400')
        c.save()

        values = content_extraction.extract('application/pdf', buf.getvalue())
        dollars = [v for v in values if v['fieldName'] == 'Dollar amount']
        self.assertEqual(len(dollars), 1)
        self.assertEqual(dollars[0]['value'], '$4,218,400')
        self.assertEqual(dollars[0]['source'], 'page 1')

    def test_pdf_corrupt_file_raises_extraction_failed(self):
        with self.assertRaises(content_extraction.ExtractionFailed):
            content_extraction.extract('application/pdf', b'this is not a real pdf file')

    def test_docx_real_extraction(self):
        import docx
        document = docx.Document()
        document.add_paragraph('Net operating income $611,200')
        buf = io.BytesIO()
        document.save(buf)

        values = content_extraction.extract(
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buf.getvalue(),
        )
        dollars = [v for v in values if v['fieldName'] == 'Dollar amount']
        self.assertEqual(len(dollars), 1)
        self.assertEqual(dollars[0]['source'], 'paragraph 1')

    def test_xlsx_direct_cell_read_full_confidence(self):
        import openpyxl
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = 'FY25'
        sheet['B7'] = 1.14
        buf = io.BytesIO()
        workbook.save(buf)

        values = content_extraction.extract(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buf.getvalue(),
        )
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]['value'], '1.14')
        self.assertEqual(values[0]['confidence'], 1.0)
        self.assertIn('FY25', values[0]['source'])
        self.assertIn('B7', values[0]['source'])

    def test_max_values_per_document_cap(self):
        text = '\n'.join(f'${i}.00' for i in range(100))
        values = content_extraction.extract('text/plain', text.encode())
        self.assertLessEqual(len(values), content_extraction.MAX_VALUES_PER_DOCUMENT)


class ExtractedValueModelTests(TestCase):
    def test_needs_review_below_threshold(self):
        doc_request = DocumentRequest.objects.create(borrower_name='X', status='draft')
        item = ChecklistItem.objects.create(document_request=doc_request, name='Item')
        upload = UploadedFile.objects.create(document_request=doc_request, checklist_item=item, file_name='a', file_type='text/plain', file_path='a')
        twin = DocumentTwin.objects.create(document_request=doc_request, uploaded_file=upload)
        low = ExtractedValue.objects.create(document_twin=twin, field_name='x', value='y', confidence=0.70)
        high = ExtractedValue.objects.create(document_twin=twin, field_name='x', value='y', confidence=0.95)
        self.assertTrue(low.needs_review)
        self.assertFalse(high.needs_review)


class DocumentTwinContentExtractionAPITests(AuthenticatedAPITestCase):
    """Step 7's real content extraction wired end-to-end through the
    advance-to-'extracted' API call (not just the pure function above)."""

    def _setup_with_first_item_content(self, file_bytes, content_type):
        doc_request = _make_sent_request(self.client, self.user)
        items = list(doc_request.checklist_items.order_by('order').all())
        self.client.force_authenticate(user=None)
        self.client.post(f'/api/upload/{doc_request.link_token}/documents', {
            'checklistItemId': items[0].id,
            'file': SimpleUploadedFile('target.dat', file_bytes, content_type=content_type),
        }, format='multipart')
        for item in items[1:]:
            self.client.post(f'/api/upload/{doc_request.link_token}/documents', {
                'checklistItemId': item.id, 'file': SimpleUploadedFile(f'{item.id}.txt', b'filler'),
            }, format='multipart')
        self.client.force_authenticate(user=self.user)
        items = list(doc_request.checklist_items.order_by('order').all())  # refresh: current_file now set
        for item in items:
            self.client.post(f'/api/requests/{doc_request.id}/parking-bay/{item.id}/review', {'decision': 'approve'}, format='json')
        self.client.post(f'/api/requests/{doc_request.id}/parking-bay/kick-start-extraction')
        twin = DocumentTwin.objects.get(document_request=doc_request, uploaded_file=items[0].current_file)
        return doc_request, twin

    def _advance(self, doc_request, twin):
        return self.client.post(f'/api/requests/{doc_request.id}/extraction/{twin.id}/advance')

    def test_real_dollar_amount_extracted_from_text_file(self):
        doc_request, twin = self._setup_with_first_item_content(b'Total revenue FY25: $4,218,400', 'text/plain')
        self._advance(doc_request, twin)  # -> classified
        res = self._advance(doc_request, twin)  # -> extracted
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        dollars = [v for v in res.data['extractedValues'] if v['fieldName'] == 'Dollar amount']
        self.assertEqual(len(dollars), 1)
        self.assertEqual(dollars[0]['value'], '$4,218,400')
        self.assertEqual(dollars[0]['confidence'], 0.95)
        self.assertFalse(dollars[0]['needsReview'])

    def test_no_extractable_values_advances_cleanly(self):
        doc_request, twin = self._setup_with_first_item_content(b'nothing extractable here', 'text/plain')
        self._advance(doc_request, twin)  # -> classified
        res = self._advance(doc_request, twin)  # -> extracted
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['extractedValues'], [])

    def test_corrupt_pdf_extraction_failure_does_not_advance_stage(self):
        doc_request, twin = self._setup_with_first_item_content(b'not a real pdf', 'application/pdf')
        self._advance(doc_request, twin)  # -> classified
        res = self._advance(doc_request, twin)  # attempt -> extracted, should fail
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        twin.refresh_from_db()
        self.assertEqual(twin.current_stage, 'classified')  # stage did NOT advance on failure
        self.assertTrue(ExtractionEvent.objects.filter(document_twin=twin, event_type='extract.failed').exists())

    def test_extraction_can_be_retried_after_a_failure(self):
        """7.7's 'doesn't hang forever' -- a failed extraction is retriable,
        not a permanent dead end."""
        doc_request, twin = self._setup_with_first_item_content(b'not a real pdf', 'application/pdf')
        self._advance(doc_request, twin)  # -> classified
        self._advance(doc_request, twin)  # fails, stays at classified

        # swap in a real, readable file at the same path and retry
        from . import storage
        storage.write_file(twin.uploaded_file.file_path, b'Filed on 01/15/2026')
        twin.uploaded_file.file_type = 'text/plain'
        twin.uploaded_file.save(update_fields=['file_type'])

        res = self._advance(doc_request, twin)  # -> extracted, should succeed now
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['currentStage'], 'extracted')

    def test_confidence_stage_reports_real_average_and_review_count(self):
        doc_request, twin = self._setup_with_first_item_content(b'filler', 'text/plain')
        self._advance(doc_request, twin)  # -> classified
        self._advance(doc_request, twin)  # -> extracted (no matches in 'filler')

        # seed known confidences directly to test the aggregate math for real,
        # without depending on OCR accuracy to produce a below-threshold value
        ExtractedValue.objects.create(document_twin=twin, field_name='Dollar amount', value='$1', confidence=0.95)
        ExtractedValue.objects.create(document_twin=twin, field_name='Ratio', value='1.0x', confidence=0.60)

        self._advance(doc_request, twin)  # -> provenance
        self._advance(doc_request, twin)  # -> confidence

        event = ExtractionEvent.objects.filter(document_twin=twin, event_type='document_twin.confidence').latest('created_at')
        avg_confidence = (0.95 + 0.60) / 2
        self.assertEqual(event.detail, f'Avg confidence {avg_confidence:.0%} -- 1 of 2 value(s) need HITL review.')


class ChecklistTemplateTests(AuthenticatedAPITestCase):
    """v3's Step 2b -- a full ~50-item checklist master template across 8
    categories, each tagged Lender (customer-facing) or Loan Admin
    (internal-only)."""

    def test_template_endpoint_requires_auth(self):
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/requests/checklist-template')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_template_groups_items_by_category_in_order(self):
        res = self.client.get('/api/requests/checklist-template')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        categories = [c['category'] for c in res.data['categories']]
        self.assertEqual(categories, checklist_module.CATEGORIES)

    def test_template_total_item_count_matches_master_list(self):
        res = self.client.get('/api/requests/checklist-template')
        total = sum(len(c['items']) for c in res.data['categories'])
        self.assertEqual(total, len(checklist_module.CHECKLIST_TEMPLATE))

    def test_template_reflects_default_selection_and_audience(self):
        res = self.client.get('/api/requests/checklist-template')
        corp_res_cat = next(c for c in res.data['categories'] if c['category'] == 'Organizational documents / financial info')
        corp_res = next(i for i in corp_res_cat['items'] if i['name'] == 'Corporate Resolution')
        self.assertTrue(corp_res['selected'])
        self.assertEqual(corp_res['audience'], 'lender')

        cert_fact = next(i for i in corp_res_cat['items'] if i['name'] == 'Certificate of Fact')
        self.assertFalse(cert_fact['selected'])
        self.assertEqual(cert_fact['audience'], 'loan_admin')


class ChecklistSelectionAtSendTests(AuthenticatedAPITestCase):
    """Sending with no `selectedItems` falls back to the template's own
    default selection; sending with an explicit selection uses exactly
    that, with the server (not the client) resolving each item's audience."""

    VALID = {
        'borrowerName': 'Priya Sharma', 'phone': '7035551234',
        'email': 'priya@meridianlogistics.com', 'companyName': 'Meridian Logistics LLC', 'action': 'send',
    }

    def test_no_selection_falls_back_to_real_default(self):
        res = self.client.post(LIST_CREATE_URL, self.VALID, format='json')
        doc_request = DocumentRequest.objects.get(id=res.data['id'])
        default_names = {name for _, name, _ in checklist_module.default_selection()}
        created_names = set(doc_request.checklist_items.values_list('name', flat=True))
        self.assertEqual(created_names, default_names)

    def test_default_selection_has_the_documented_lender_loan_admin_split(self):
        res = self.client.post(LIST_CREATE_URL, self.VALID, format='json')
        doc_request = DocumentRequest.objects.get(id=res.data['id'])
        self.assertEqual(doc_request.checklist_items.filter(audience='lender').count(), 12)
        self.assertEqual(doc_request.checklist_items.filter(audience='loan_admin').count(), 15)

    def test_explicit_selection_creates_exactly_those_items(self):
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'selectedItems': TEST_CHECKLIST_SELECTION}, format='json')
        doc_request = DocumentRequest.objects.get(id=res.data['id'])
        names = list(doc_request.checklist_items.order_by('order').values_list('name', flat=True))
        self.assertEqual(names, TEST_CHECKLIST_NAMES)

    def test_audience_is_server_resolved_not_client_supplied(self):
        """The client payload shape only ever carries {category, name} --
        even if a caller stuffs an 'audience' key in, the server looks up
        the real audience from the template instead of trusting it."""
        forged = [{'category': 'Organizational documents / financial info', 'name': 'Corporate Resolution', 'audience': 'loan_admin'}]
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'selectedItems': forged}, format='json')
        doc_request = DocumentRequest.objects.get(id=res.data['id'])
        item = doc_request.checklist_items.get(name='Corporate Resolution')
        self.assertEqual(item.audience, 'lender')  # template says lender, not the forged 'loan_admin'

    def test_unknown_checklist_item_is_rejected(self):
        bogus = [{'category': 'Organizational documents / financial info', 'name': 'Not A Real Item'}]
        res = self.client.post(LIST_CREATE_URL, {**self.VALID, 'selectedItems': bogus}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DocumentRequest.objects.filter(email=self.VALID['email']).exists())

    def test_sending_uses_the_bankers_saved_preference_when_no_explicit_selection(self):
        """v5: the checklist is configured once under Profile settings, not
        rebuilt per request -- a plain 'Send secure request' (no
        selectedItems in the body at all) must use whatever the banker
        saved there, not the template's own default."""
        self.client.post('/api/requests/checklist-preference', {'selectedItems': TEST_CHECKLIST_SELECTION}, format='json')

        res = self.client.post(LIST_CREATE_URL, self.VALID, format='json')
        doc_request = DocumentRequest.objects.get(id=res.data['id'])
        names = list(doc_request.checklist_items.order_by('order').values_list('name', flat=True))
        self.assertEqual(names, TEST_CHECKLIST_NAMES)


class ChecklistPreferenceTests(AuthenticatedAPITestCase):
    """v5's Profile settings > Document checklist -- a banker's saved
    default, configured once rather than rebuilt per request."""

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/requests/checklist-preference')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_falls_back_to_template_default_when_nothing_saved(self):
        res = self.client.get('/api/requests/checklist-preference')
        self.assertFalse(res.data['isSaved'])
        names = {i['name'] for i in res.data['selectedItems']}
        default_names = {name for _, name, _ in checklist_module.default_selection()}
        self.assertEqual(names, default_names)

    def test_save_and_get_round_trips(self):
        self.client.post('/api/requests/checklist-preference', {'selectedItems': TEST_CHECKLIST_SELECTION}, format='json')
        res = self.client.get('/api/requests/checklist-preference')
        self.assertTrue(res.data['isSaved'])
        names = [i['name'] for i in res.data['selectedItems']]
        self.assertEqual(names, TEST_CHECKLIST_NAMES)

    def test_save_rejects_unknown_item(self):
        bogus = [{'category': 'Organizational documents / financial info', 'name': 'Not A Real Item'}]
        res = self.client.post('/api/requests/checklist-preference', {'selectedItems': bogus}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ChecklistPreference.objects.filter(banker=self.user).exists())

    def test_save_rejects_empty_selection(self):
        res = self.client.post('/api/requests/checklist-preference', {'selectedItems': []}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resaving_overwrites_not_duplicates(self):
        self.client.post('/api/requests/checklist-preference', {'selectedItems': TEST_CHECKLIST_SELECTION}, format='json')
        other_selection = [{'category': 'Initial loan documents', 'name': 'Risk Rating Form'}]
        self.client.post('/api/requests/checklist-preference', {'selectedItems': other_selection}, format='json')

        self.assertEqual(ChecklistPreference.objects.filter(banker=self.user).count(), 1)
        res = self.client.get('/api/requests/checklist-preference')
        self.assertEqual([i['name'] for i in res.data['selectedItems']], ['Risk Rating Form'])

    def test_preference_is_per_banker(self):
        self.client.post('/api/requests/checklist-preference', {'selectedItems': TEST_CHECKLIST_SELECTION}, format='json')
        other_banker = User.objects.create_user(username='other@freedombankva.com', email='other@freedombankva.com', password='x')
        self.client.force_authenticate(user=other_banker)
        res = self.client.get('/api/requests/checklist-preference')
        self.assertFalse(res.data['isSaved'])  # other banker has no saved preference of their own


class LenderLoanAdminSplitTests(AuthenticatedAPITestCase):
    """Loan Admin items are tracked as real ChecklistItem rows (banker-side)
    but never shown to the customer and never block completion, since
    there's no upload mechanism for them yet."""

    def setUp(self):
        super().setUp()
        self.selection = [
            {'category': 'Organizational documents / financial info', 'name': 'Corporate Resolution'},  # lender
            {'category': 'Organizational documents / financial info', 'name': 'Certificate of Good Standing'},  # loan_admin
        ]
        self.doc_request = _make_sent_request(self.client, self.user, selectedItems=self.selection)
        self.lender_item = self.doc_request.checklist_items.get(audience='lender')
        self.loan_admin_item = self.doc_request.checklist_items.get(audience='loan_admin')

    def test_upload_portal_never_shows_loan_admin_items(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(f'/api/upload/{self.doc_request.link_token}')
        names = [i['name'] for i in res.data['items']]
        self.assertIn('Corporate Resolution', names)
        self.assertNotIn('Certificate of Good Standing', names)

    def test_customer_cannot_upload_against_a_loan_admin_item(self):
        self.client.force_authenticate(user=None)
        res = self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': self.loan_admin_item.id, 'file': SimpleUploadedFile('x.pdf', b'x'),
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.loan_admin_item.refresh_from_db()
        self.assertEqual(self.loan_admin_item.status, 'pending')

    def test_uploads_complete_once_all_lender_items_done_even_with_loan_admin_pending(self):
        self.client.force_authenticate(user=None)
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': self.lender_item.id, 'file': SimpleUploadedFile('x.pdf', b'x'),
        }, format='multipart')
        self.doc_request.refresh_from_db()
        self.assertEqual(self.doc_request.status, 'uploads_complete')
        self.loan_admin_item.refresh_from_db()
        self.assertEqual(self.loan_admin_item.status, 'pending')  # stays pending forever -- no upload path yet

    def test_parking_bay_excludes_loan_admin_items(self):
        self.client.force_authenticate(user=None)
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': self.lender_item.id, 'file': SimpleUploadedFile('x.pdf', b'x'),
        }, format='multipart')
        self.client.force_authenticate(user=self.user)
        res = self.client.get(f'/api/requests/{self.doc_request.id}/parking-bay')
        names = [i['name'] for i in res.data['items']]
        self.assertIn('Corporate Resolution', names)
        self.assertNotIn('Certificate of Good Standing', names)

    def test_review_complete_ignores_loan_admin_items(self):
        """Review-completeness must be reachable even though the Loan Admin
        item never gets a file -- otherwise Step 6 could never finish."""
        self.client.force_authenticate(user=None)
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': self.lender_item.id, 'file': SimpleUploadedFile('x.pdf', b'x'),
        }, format='multipart')
        self.client.force_authenticate(user=self.user)
        self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/{self.lender_item.id}/review', {
            'decision': 'approve',
        }, format='json')
        res = self.client.get(f'/api/requests/{self.doc_request.id}/parking-bay')
        self.assertTrue(res.data['reviewComplete'])

    def test_email_never_mentions_loan_admin_items(self):
        email = RequestEmail.objects.get(document_request=self.doc_request, kind='request')
        self.assertIn('Corporate Resolution', email.body_text)
        self.assertNotIn('Certificate of Good Standing', email.body_text)


class CustomerActivityTests(AuthenticatedAPITestCase):
    """v5's 'Customer activity' tab -- a real, chronological event trail per
    request, built entirely from data already logged elsewhere (no search,
    no portfolio analytics, no tickler/covenant widgets -- those need
    infrastructure this project doesn't have)."""

    def setUp(self):
        super().setUp()
        self.doc_request = _make_sent_request(self.client, self.user)
        self.items = list(self.doc_request.checklist_items.order_by('order').all())

    def _get_activity(self):
        res = self.client.get('/api/requests/activity')
        return next(r for r in res.data['requests'] if r['id'] == self.doc_request.id)

    def test_activity_requires_auth(self):
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/requests/activity')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_activity_excludes_drafts(self):
        draft = DocumentRequest.objects.create(borrower_name='Nobody Yet', status='draft', created_by=self.user)
        res = self.client.get('/api/requests/activity')
        ids = [r['id'] for r in res.data['requests']]
        self.assertNotIn(draft.id, ids)
        self.assertIn(self.doc_request.id, ids)

    def test_activity_includes_the_sent_email_event(self):
        row = self._get_activity()
        titles = [e['title'] for e in row['events']]
        self.assertIn('Secure request sent', titles)

    def test_activity_includes_upload_and_review_events_in_chronological_order(self):
        item = self.items[0]
        self.client.force_authenticate(user=None)
        self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('statement.pdf', b'content'),
        }, format='multipart')
        self.client.force_authenticate(user=self.user)
        self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/{item.id}/review', {
            'decision': 'flag', 'comment': 'needs redo',
        }, format='json')

        row = self._get_activity()
        titles = [e['title'] for e in row['events']]
        self.assertIn('statement.pdf uploaded', titles)
        self.assertIn('statement.pdf flagged for re-upload', titles)

        timestamps = [e['at'] for e in row['events']]
        self.assertEqual(timestamps, sorted(timestamps))  # chronological, oldest first

        flag_event = next(e for e in row['events'] if e['title'] == 'statement.pdf flagged for re-upload')
        self.assertEqual(flag_event['type'], 'bank')
        self.assertEqual(flag_event['detail'], 'needs redo')

    def test_activity_twin_events_included_but_audit_write_excluded(self):
        for item in self.items:
            self.client.force_authenticate(user=None)
            self.client.post(f'/api/upload/{self.doc_request.link_token}/documents', {
                'checklistItemId': item.id, 'file': SimpleUploadedFile(f'{item.id}.pdf', b'content'),
            }, format='multipart')
            self.client.force_authenticate(user=self.user)
            self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/{item.id}/review', {
                'decision': 'approve',
            }, format='json')
        self.client.post(f'/api/requests/{self.doc_request.id}/parking-bay/kick-start-extraction')

        row = self._get_activity()
        types = {e['title'] for e in row['events']}
        self.assertIn('document_twin.received', types)
        self.assertIn('business_twin.relationship', types)
        self.assertNotIn('audit.write', types)


class NeedsAttentionTests(AuthenticatedAPITestCase):
    """v5's 'Needs attention' rail -- every item is real: fraud-stopped
    sessions, flagged documents, and low-confidence extracted values. No
    tickler-escalation item is included since no reminder system exists."""

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/requests/needs-attention')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_empty_when_nothing_needs_attention(self):
        _make_sent_request(self.client, self.user)
        res = self.client.get('/api/requests/needs-attention')
        self.assertEqual(res.data['items'], [])

    def test_fraud_stopped_request_surfaces(self):
        doc_request = _make_sent_request(self.client, self.user)
        self.client.force_authenticate(user=None)
        for _ in range(5):
            self.client.post(f'/api/upload/{doc_request.link_token}/documents', {}, format='multipart')
        self.client.force_authenticate(user=self.user)

        res = self.client.get('/api/requests/needs-attention')
        fraud_items = [i for i in res.data['items'] if i['type'] == 'fraud']
        self.assertEqual(len(fraud_items), 1)
        self.assertEqual(fraud_items[0]['requestId'], doc_request.id)
        self.assertIn('Repeated failed upload attempts', fraud_items[0]['detail'])

    def test_flagged_document_surfaces(self):
        doc_request = _make_sent_request(self.client, self.user)
        item = doc_request.checklist_items.first()
        self.client.force_authenticate(user=None)
        self.client.post(f'/api/upload/{doc_request.link_token}/documents', {
            'checklistItemId': item.id, 'file': SimpleUploadedFile('x.pdf', b'x'),
        }, format='multipart')
        self.client.force_authenticate(user=self.user)
        self.client.post(f'/api/requests/{doc_request.id}/parking-bay/{item.id}/review', {
            'decision': 'flag', 'comment': 'needs redo',
        }, format='json')

        res = self.client.get('/api/requests/needs-attention')
        flagged_items = [i for i in res.data['items'] if i['type'] == 'flagged']
        self.assertEqual(len(flagged_items), 1)
        self.assertEqual(flagged_items[0]['requestId'], doc_request.id)
        self.assertEqual(flagged_items[0]['detail'], 'needs redo')

    def test_low_confidence_values_surface_as_a_single_hitl_count(self):
        doc_request = _make_sent_request(self.client, self.user)
        item = doc_request.checklist_items.first()
        upload = UploadedFile.objects.create(
            document_request=doc_request, checklist_item=item,
            file_name='a.pdf', file_type='text/plain', file_path='a',
        )
        twin = DocumentTwin.objects.create(document_request=doc_request, uploaded_file=upload)
        ExtractedValue.objects.create(document_twin=twin, field_name='x', value='y', confidence=0.5)
        ExtractedValue.objects.create(document_twin=twin, field_name='x', value='y', confidence=0.95)

        res = self.client.get('/api/requests/needs-attention')
        hitl_items = [i for i in res.data['items'] if i['type'] == 'hitl']
        self.assertEqual(len(hitl_items), 1)
        self.assertIn('1 value(s)', hitl_items[0]['title'])


class SearchTests(AuthenticatedAPITestCase):
    """v5's document-estate search -- real substring matching, no
    semantic/AI search infrastructure exists."""

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/requests/search?q=Meridian')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_empty_query_returns_no_results(self):
        res = self.client.get('/api/requests/search?q=')
        self.assertEqual(res.data['results'], [])

    def test_matches_request_by_company_name(self):
        _make_sent_request(self.client, self.user, companyName='Meridian Logistics LLC')
        res = self.client.get('/api/requests/search?q=meridian')
        matches = [r for r in res.data['results'] if r['kind'] == 'request']
        self.assertEqual(len(matches), 1)
        self.assertIn('Meridian', matches[0]['title'])

    def test_matches_checklist_item_name(self):
        doc_request = _make_sent_request(self.client, self.user)
        res = self.client.get('/api/requests/search?q=Corporate Resolution')
        matches = [r for r in res.data['results'] if r['kind'] == 'checklistItem']
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['requestId'], doc_request.id)

    def test_matches_extracted_value(self):
        doc_request = _make_sent_request(self.client, self.user)
        item = doc_request.checklist_items.first()
        upload = UploadedFile.objects.create(
            document_request=doc_request, checklist_item=item,
            file_name='a.pdf', file_type='text/plain', file_path='a',
        )
        twin = DocumentTwin.objects.create(document_request=doc_request, uploaded_file=upload)
        ExtractedValue.objects.create(document_twin=twin, field_name='Dollar amount', value='$4,218,400', confidence=0.95)

        res = self.client.get('/api/requests/search?q=4,218,400')
        matches = [r for r in res.data['results'] if r['kind'] == 'extractedValue']
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['requestId'], doc_request.id)

    def test_no_match_returns_empty(self):
        _make_sent_request(self.client, self.user)
        res = self.client.get('/api/requests/search?q=nonexistentxyz')
        self.assertEqual(res.data['results'], [])


class MailDeliveryTests(TestCase):
    """document_requests/mail_delivery.py -- real direct-to-MX delivery
    logic (mirrors the sibling StackPulse project's approach), with
    smtplib.SMTP mocked out so tests never touch the real network."""

    def setUp(self):
        mail_delivery.clear_mx_cache()

    @override_settings(MAIL_ENABLED=False, MAIL_ALLOWED_DOMAINS={'example.com'})
    def test_disabled_returns_not_attempted_without_calling_smtp(self):
        with patch('document_requests.mail_delivery.smtplib.SMTP') as mock_smtp:
            attempted, delivered = mail_delivery.send_direct_email('a@example.com', 'Subject', 'Body')
        self.assertFalse(attempted)
        self.assertFalse(delivered)
        mock_smtp.assert_not_called()

    @override_settings(MAIL_ENABLED=True, MAIL_ALLOWED_DOMAINS=set())
    def test_domain_not_allowed_returns_not_attempted(self):
        with patch('document_requests.mail_delivery.smtplib.SMTP') as mock_smtp:
            attempted, delivered = mail_delivery.send_direct_email('a@notallowed.com', 'Subject', 'Body')
        self.assertFalse(attempted)
        self.assertFalse(delivered)
        mock_smtp.assert_not_called()

    @override_settings(MAIL_ENABLED=True, MAIL_ALLOWED_DOMAINS={'example.com'}, MAIL_TEST_SERVER='stub-host:2525')
    def test_allowed_domain_sends_via_real_smtp_protocol_calls(self):
        """MAIL_TEST_SERVER bypasses real MX resolution (same escape hatch
        StackPulse uses) -- this exercises the real EHLO/STARTTLS/sendmail
        call sequence against a mocked SMTP connection."""
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.has_extn.return_value = True
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_smtp_instance
        with patch('document_requests.mail_delivery.smtplib.SMTP', return_value=mock_smtp_cm) as mock_smtp:
            attempted, delivered = mail_delivery.send_direct_email('a@example.com', 'Subject', 'Body text')

        self.assertTrue(attempted)
        self.assertTrue(delivered)
        mock_smtp.assert_called_once_with('stub-host', 2525, timeout=10)
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.sendmail.assert_called_once()
        to_addr = mock_smtp_instance.sendmail.call_args[0][1]
        self.assertEqual(to_addr, ['a@example.com'])

    @override_settings(MAIL_ENABLED=True, MAIL_ALLOWED_DOMAINS={'example.com'}, MAIL_TEST_SERVER='stub-host:2525')
    def test_smtp_failure_returns_attempted_not_delivered_and_does_not_raise(self):
        import smtplib as smtplib_module
        with patch('document_requests.mail_delivery.smtplib.SMTP', side_effect=smtplib_module.SMTPConnectError(421, 'refused')):
            attempted, delivered = mail_delivery.send_direct_email('a@example.com', 'Subject', 'Body')
        self.assertTrue(attempted)  # a real SMTP conversation was genuinely opened
        self.assertFalse(delivered)  # ...but it failed -- never raises either way

    def test_mx_resolution_uses_dns_and_caches(self):
        fake_record = MagicMock(preference=10, exchange='mail.example.com.')
        with patch('document_requests.mail_delivery.dns.resolver.resolve', return_value=[fake_record]) as mock_resolve:
            host1 = mail_delivery._resolve_mx('example.com')
            host2 = mail_delivery._resolve_mx('example.com')
        self.assertEqual(host1, 'mail.example.com')  # trailing dot stripped
        self.assertEqual(host2, 'mail.example.com')
        mock_resolve.assert_called_once()  # second call served from cache

    def test_mx_resolution_falls_back_to_domain_on_dns_failure(self):
        with patch('document_requests.mail_delivery.dns.resolver.resolve', side_effect=Exception('no DNS')):
            host = mail_delivery._resolve_mx('unresolvable-domain.test')
        self.assertEqual(host, 'unresolvable-domain.test')


class EmailDeliveryIntegrationTests(AuthenticatedAPITestCase):
    """email_service.py's real integration with mail_delivery.py -- the
    RequestEmail audit row is always created, and delivery_attempted/
    delivered reflect what mail_delivery.send_direct_email actually did."""

    @override_settings(MAIL_ENABLED=True, MAIL_ALLOWED_DOMAINS={'meridianlogistics.com'}, MAIL_TEST_SERVER='stub-host:2525')
    def test_successful_delivery_is_recorded_on_the_audit_row(self):
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.has_extn.return_value = False
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_smtp_instance
        with patch('document_requests.mail_delivery.smtplib.SMTP', return_value=mock_smtp_cm):
            _make_sent_request(self.client, self.user)

        email = RequestEmail.objects.get(kind='request')
        self.assertTrue(email.delivery_attempted)
        self.assertTrue(email.delivered)

    @override_settings(MAIL_ENABLED=True, MAIL_ALLOWED_DOMAINS={'meridianlogistics.com'}, MAIL_TEST_SERVER='stub-host:2525')
    def test_failed_delivery_still_creates_the_audit_row(self):
        with patch('document_requests.mail_delivery.smtplib.SMTP', side_effect=OSError('connection refused')):
            _make_sent_request(self.client, self.user)

        email = RequestEmail.objects.get(kind='request')
        self.assertTrue(email.delivery_attempted)
        self.assertFalse(email.delivered)
        self.assertTrue(email.body_text)  # the audit trail is intact regardless of delivery outcome

    def test_disabled_by_default_in_tests_records_neither_attempted_nor_delivered(self):
        """Guards the module-level MAIL_ENABLED=False override itself --
        confirms delivery is genuinely skipped (not just failed) in the
        normal test run, not just in the tests that explicitly re-enable it
        above."""
        _make_sent_request(self.client, self.user)
        email = RequestEmail.objects.get(kind='request')
        self.assertFalse(email.delivery_attempted)
        self.assertFalse(email.delivered)
