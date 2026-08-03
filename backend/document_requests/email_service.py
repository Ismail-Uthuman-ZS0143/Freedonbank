"""Compose, log, and deliver emails: the Step 3 secure request email, the
Step 4 fraud/session-guard alert, the Step 5 completion confirmation, and
the Step 6 batched review-flags re-request -- all reuse the same
RequestEmail log table and the same real delivery path.

Every email is composed and persisted as an append-only RequestEmail row
regardless of delivery outcome (so it's always inspectable via the admin or
the API), and real delivery is then attempted through
document_requests/mail_delivery.py -- direct-to-MX, no SMTP relay/provider
account, mirroring the pattern already used in the sibling StackPulse
project. Delivery never raises; `RequestEmail.delivery_attempted`/
`delivered` record what actually happened.
"""
import logging

from django.conf import settings

from .mail_delivery import send_direct_email
from .models import RequestEmail

logger = logging.getLogger(__name__)

FROM_EMAIL = settings.MAIL_FROM_ADDRESS


def _log_and_deliver(*, document_request, kind, to_email, from_email, subject, body_text):
    """Creates the audit row, then attempts real delivery and updates it
    with the outcome. Always returns the RequestEmail row -- delivery
    failure never prevents the audit trail or the caller's flow."""
    email = RequestEmail.objects.create(
        document_request=document_request, kind=kind,
        to_email=to_email, from_email=from_email,
        subject=subject, body_text=body_text,
    )

    attempted, delivered = send_direct_email(to_email, subject, body_text)
    email.delivery_attempted = attempted
    email.delivered = delivered
    email.save(update_fields=['delivery_attempted', 'delivered'])

    logger.info(
        'Email %s: request_id=%s kind=%s to=%s subject=%r',
        'delivered' if delivered else ('delivery failed' if attempted else 'delivery skipped'),
        document_request.id, kind, to_email, subject,
    )

    return email


def _compose_body(doc_request):
    # Only Lender (customer-facing) items ever appear in the customer's
    # email -- Loan Admin items are internal-only and never listed here.
    lender_items = list(doc_request.checklist_items.filter(audience='lender').order_by('order'))
    checklist_lines = '\n'.join(f'  - {item.name}' for item in lender_items)
    expires = doc_request.link_expires_at.strftime('%b %d, %Y') if doc_request.link_expires_at else 'unknown'
    upload_url = f'{settings.FRONTEND_BASE_URL}/upload/{doc_request.link_token}'

    return (
        f'Dear {doc_request.borrower_name},\n\n'
        f'Thank you for choosing Freedom Bank of Virginia for {doc_request.company_name}. '
        f'To begin processing your commercial loan application, we need the following documents for this cycle:\n\n'
        f'Required documents · {len(lender_items)}\n'
        f'{checklist_lines}\n\n'
        f'Upload them through our secure portal. The link below is unique to you, works for this '
        f'request only, and expires in 7 days.\n\n'
        f'{upload_url}\n'
        f'Link expires {expires} · single-purpose · encrypted\n\n'
        f"If you didn't expect this email, contact your relationship manager directly. Freedom Bank "
        f'will never ask for your password or one-time codes by email.\n\n'
        f'Warm regards,\n'
        f'Commercial Lending Team\n'
        f'Freedom Bank of Virginia · 10555 Main St., Fairfax, VA'
    )


def send_secure_request_email(doc_request):
    """Composes, logs, and attempts real delivery of the Step 3 email for a
    just-sent or just-resent DocumentRequest. Returns the RequestEmail row."""
    subject = 'Documents needed to begin your loan application'
    body = _compose_body(doc_request)
    return _log_and_deliver(
        document_request=doc_request, kind='request',
        to_email=doc_request.email, from_email=FROM_EMAIL,
        subject=subject, body_text=body,
    )


def log_fraud_alert_email(doc_request, reason):
    """Step 4's 'your relationship manager has been notified' -- addressed
    to the banker who created the request instead of the customer."""
    banker_email = doc_request.created_by.email if doc_request.created_by_id else 'unknown-banker@freedombankva.com'
    subject = f'Session ended — unusual activity detected · request #{doc_request.id}'
    body = (
        f'The upload session for {doc_request.borrower_name} ({doc_request.company_name}) was '
        f'automatically ended.\n\n'
        f'Reason: {reason}\n\n'
        f'Documents already uploaded before this point remain safely in the parking bay -- nothing '
        f'was lost. Contact the customer directly to continue securely if appropriate.'
    )
    return _log_and_deliver(
        document_request=doc_request, kind='fraud_alert',
        to_email=banker_email, from_email='alerts@freedombankva.com',
        subject=subject, body_text=body,
    )


def log_completion_confirmation_email(doc_request):
    """Step 5: 'Completion thanks the customer and triggers an automatic
    confirmation email from the platform.' Fires once, the moment the last
    checklist item is uploaded (see upload_document_view)."""
    subject = 'Your documents have been received — Freedom Bank of Virginia'
    body = (
        f'Dear {doc_request.borrower_name},\n\n'
        f'Thanks for uploading. All documents for {doc_request.company_name} are now in our secure '
        f'parking bay. The FBOV team will review them and reach out with next steps on your '
        f'application.\n\n'
        f'Reference {doc_request.reference_number}\n\n'
        f'Warm regards,\n'
        f'Commercial Lending Team\n'
        f'Freedom Bank of Virginia · 10555 Main St., Fairfax, VA'
    )
    return _log_and_deliver(
        document_request=doc_request, kind='confirmation',
        to_email=doc_request.email, from_email=FROM_EMAIL,
        subject=subject, body_text=body,
    )


def log_review_flags_email(doc_request, flagged_items):
    """Step 6's 'Send secure email · N flagged comment(s)' -- bundles every
    currently-flagged document's reviewer comment into a single email to the
    customer (never one email per flag). `flagged_items` is a list of
    ChecklistItem rows whose current_file.review_status == 'flagged'."""
    lines = '\n'.join(
        f'  - {item.name}: {item.current_file.review_comment}' for item in flagged_items
    )
    subject = f'Action needed — {len(flagged_items)} document(s) need a re-upload'
    body = (
        f'Dear {doc_request.borrower_name},\n\n'
        f'Thanks for your recent upload. Our team reviewed your documents for {doc_request.company_name} '
        f'and needs the following re-uploaded:\n\n'
        f'{lines}\n\n'
        f'Please sign back in to your secure upload link to replace these documents.\n\n'
        f'Reference {doc_request.reference_number}\n\n'
        f'Warm regards,\n'
        f'Commercial Lending Team\n'
        f'Freedom Bank of Virginia · 10555 Main St., Fairfax, VA'
    )
    return _log_and_deliver(
        document_request=doc_request, kind='review_flags',
        to_email=doc_request.email, from_email=FROM_EMAIL,
        subject=subject, body_text=body,
    )


def log_discrepancy_email(doc_request, twin, comment):
    """Step 8's 'Send secure email with review comments' -- the HITL
    comment is included verbatim (per the mockup copy), addressed to the
    customer, referencing the specific document twin it's about."""
    subject = f'A document needs your attention — {doc_request.reference_number}'
    body = (
        f'Dear {doc_request.borrower_name},\n\n'
        f'Our team reviewed {twin.uploaded_file.file_name} for {doc_request.company_name} and found '
        f'something that needs your attention:\n\n'
        f'{comment}\n\n'
        f'Reference {doc_request.reference_number}\n\n'
        f'Warm regards,\n'
        f'Commercial Lending Team\n'
        f'Freedom Bank of Virginia · 10555 Main St., Fairfax, VA'
    )
    return _log_and_deliver(
        document_request=doc_request, kind='discrepancy',
        to_email=doc_request.email, from_email=FROM_EMAIL,
        subject=subject, body_text=body,
    )
