"""Compose and log emails: the Step 3 secure request email, the Step 4
fraud/session-guard alert, the Step 5 completion confirmation, and the
Step 6 batched review-flags re-request -- all reuse the same RequestEmail
log table.

No real mail provider is wired up (SMTP/SendGrid/etc.) -- per direction,
this logs the exact content instead of faking delivery, the same "honest
placeholder" pattern used for SSO/MFA in Step 1.
"""
import logging

from django.conf import settings

from .models import RequestEmail

logger = logging.getLogger(__name__)

FROM_EMAIL = 'requests@freedombankva.com'


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
    """'Sends' (composes + logs) the Step 3 email for a just-sent or
    just-resent DocumentRequest. Returns the created RequestEmail row."""
    subject = 'Documents needed to begin your loan application'
    body = _compose_body(doc_request)

    email = RequestEmail.objects.create(
        document_request=doc_request,
        kind='request',
        to_email=doc_request.email,
        from_email=FROM_EMAIL,
        subject=subject,
        body_text=body,
    )

    logger.info(
        'Secure request email logged (not actually sent -- no mail provider configured): '
        'request_id=%s to=%s subject=%r', doc_request.id, doc_request.email, subject,
    )

    return email


def log_fraud_alert_email(doc_request, reason):
    """Step 4's 'your relationship manager has been notified' -- reuses the
    same log-only mechanism as the request email, addressed to the banker
    who created the request instead of the customer."""
    banker_email = doc_request.created_by.email if doc_request.created_by_id else 'unknown-banker@freedombankva.com'
    subject = f'Session ended — unusual activity detected · request #{doc_request.id}'
    body = (
        f'The upload session for {doc_request.borrower_name} ({doc_request.company_name}) was '
        f'automatically ended.\n\n'
        f'Reason: {reason}\n\n'
        f'Documents already uploaded before this point remain safely in the parking bay -- nothing '
        f'was lost. Contact the customer directly to continue securely if appropriate.'
    )

    email = RequestEmail.objects.create(
        document_request=doc_request,
        kind='fraud_alert',
        to_email=banker_email,
        from_email='alerts@freedombankva.com',
        subject=subject,
        body_text=body,
    )

    logger.warning(
        'Fraud/session-guard alert logged (not actually sent -- no mail provider configured): '
        'request_id=%s reason=%r', doc_request.id, reason,
    )

    return email


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

    email = RequestEmail.objects.create(
        document_request=doc_request,
        kind='confirmation',
        to_email=doc_request.email,
        from_email=FROM_EMAIL,
        subject=subject,
        body_text=body,
    )

    logger.info(
        'Completion confirmation email logged (not actually sent -- no mail provider configured): '
        'request_id=%s reference=%s to=%s', doc_request.id, doc_request.reference_number, doc_request.email,
    )

    return email


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

    email = RequestEmail.objects.create(
        document_request=doc_request, kind='review_flags',
        to_email=doc_request.email, from_email=FROM_EMAIL,
        subject=subject, body_text=body,
    )

    logger.info(
        'Review-flags email logged (not actually sent -- no mail provider configured): '
        'request_id=%s flagged_count=%d', doc_request.id, len(flagged_items),
    )

    return email
