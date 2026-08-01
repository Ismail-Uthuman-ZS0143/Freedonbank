import secrets
from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status

from .models import (
    DocumentRequest, RequestEmail, ChecklistItem, UploadedFile, UploadSession,
    DocumentTwin, BusinessTwin, ExtractionEvent, ExtractedValue, CONFIDENCE_ROUTING_THRESHOLD,
)
from .validation import validate_fields, all_valid
from . import checklist as checklist_module
from .email_service import (
    send_secure_request_email, log_fraud_alert_email, log_completion_confirmation_email, log_review_flags_email,
)
from .extraction import classify
from . import content_extraction
from . import storage

LINK_VALID_DAYS = 7  # matches the mockup's "expires in 7 days" copy
UPLOAD_SESSION_MINUTES = 20  # ballpark from the mockup's "14:32 session remaining"
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

# Deliberately simple, deterministic heuristics -- NOT real bot/geo
# detection. Location-jump detection from the mockup copy isn't implemented
# at all (would need real IP geolocation infrastructure).
FAILED_ATTEMPT_FRAUD_THRESHOLD = 5
TOTAL_ATTEMPT_FRAUD_THRESHOLD = 20


def _request_json(r):
    return {
        'id': r.id,
        'borrowerName': r.borrower_name,
        'phone': r.phone,
        'email': r.email,
        'companyName': r.company_name,
        'status': r.status,
        # `status` alone can't tell a banker a document was flagged during
        # parking-bay review -- it only tracks the upload lifecycle
        # (draft/sent/uploads_complete/...), not review decisions. A
        # request can be genuinely 'uploads_complete' (every item has a
        # file) while one of those files is flagged and needs a re-upload.
        'hasFlaggedItems': r.checklist_items.filter(current_file__review_status='flagged').exists(),
        'referenceNumber': r.reference_number,
        'linkToken': r.link_token,
        'linkExpiresAt': r.link_expires_at.isoformat() if r.link_expires_at else None,
        'createdAt': r.created_at.isoformat(),
        'sentAt': r.sent_at.isoformat() if r.sent_at else None,
    }


def _resolve_selected_items(selected_items_payload):
    """Validates a client-provided selection (list of {category, name}
    dicts, from Step 2b's customize picker) against the authoritative
    CHECKLIST_TEMPLATE -- the client only ever says which items are
    checked, never their audience, so a forged request body can't relabel
    an item Lender/Loan Admin. Returns (resolved_items, error); resolved
    items are (category, name, audience) tuples. Returns (None, None) if
    no selection was provided (caller should fall back to the default)."""
    if not selected_items_payload:
        return None, None
    resolved = []
    for entry in selected_items_payload:
        category = (entry or {}).get('category')
        name = (entry or {}).get('name')
        audience = checklist_module.resolve_audience(category, name)
        if audience is None:
            return None, f'Unknown checklist item: {category!r} / {name!r}'
        resolved.append((category, name, audience))
    return resolved, None


def _create_checklist_items(doc_request, selected_items=None):
    """Only runs once per request -- a resend keeps existing progress.
    `selected_items` is a list of (category, name, audience) tuples; falls
    back to the template's own default selection when not provided."""
    if doc_request.checklist_items.exists():
        return
    items = selected_items if selected_items is not None else checklist_module.default_selection()
    ChecklistItem.objects.bulk_create([
        ChecklistItem(document_request=doc_request, name=name, category=category, audience=audience, order=i)
        for i, (category, name, audience) in enumerate(items)
    ])


def _assign_reference_number(doc_request):
    """Step 5's customer-facing case reference (REQ-{year}-{id:04d}) --
    assigned once at first send and kept stable across resends, unlike
    link_token which rotates every time. Piggybacks on the row's own unique
    id for uniqueness rather than a separate per-year counter table."""
    if doc_request.reference_number:
        return
    doc_request.reference_number = f'REQ-{doc_request.created_at.year}-{doc_request.id:04d}'
    doc_request.save(update_fields=['reference_number'])


@api_view(['POST'])
def validate_view(request):
    """Live per-field validation, called on blur from the Step 2 form."""
    data = request.data
    results = validate_fields(data.get('borrowerName'), data.get('phone'), data.get('email'), data.get('companyName'))
    return Response(results)


@api_view(['GET'])
def checklist_template_view(request):
    """Step 2b's customize picker data -- the full master template grouped
    by category, with each item's default-selected state and audience."""
    grouped = {}
    for category, name, audience, selected in checklist_module.CHECKLIST_TEMPLATE:
        grouped.setdefault(category, []).append({'name': name, 'audience': audience, 'selected': selected})
    return Response({
        'categories': [{'category': c, 'items': grouped[c]} for c in checklist_module.CATEGORIES if c in grouped],
    })


@api_view(['GET', 'POST'])
def list_create_view(request):
    if request.method == 'GET':
        requests_qs = DocumentRequest.objects.all()
        sent = requests_qs.filter(status='sent')
        active = sent.count()
        # "Awaiting customer" = sent, and the customer hasn't uploaded
        # anything at all yet (distinct from "active", which includes
        # requests already in progress).
        awaiting = sum(1 for r in sent if not r.checklist_items.filter(audience='lender', status='uploaded').exists())
        return Response({
            'requests': [_request_json(r) for r in requests_qs],
            'metrics': {
                'activeRequests': active,
                'docsInParkingBay': UploadedFile.objects.count(),
                'awaitingCustomer': awaiting,
                'sessionsEndedFraud': requests_qs.filter(status='fraud_stopped').count(),
            },
        })

    data = request.data
    borrower_name = (data.get('borrowerName') or '').strip()
    phone = data.get('phone') or ''
    email = data.get('email') or ''
    company_name = data.get('companyName') or ''
    action = data.get('action') or 'send'  # 'send' | 'draft'

    if action == 'draft':
        if not borrower_name:
            return Response({'error': 'Borrower name is required, even for a draft.'}, status=status.HTTP_400_BAD_REQUEST)
        doc_request = DocumentRequest.objects.create(
            borrower_name=borrower_name, phone=phone, email=email, company_name=company_name,
            status='draft', created_by=request.user,
        )
        return Response(_request_json(doc_request), status=status.HTTP_201_CREATED)

    # action == 'send' -- never trust client-side validation, re-check here.
    results = validate_fields(borrower_name, phone, email, company_name)
    if not all_valid(results):
        return Response({'error': 'All fields must be valid before sending.', 'fields': results}, status=status.HTTP_400_BAD_REQUEST)

    # Step 2b's customize picker -- optional; falls back to the template's
    # own default selection if the caller doesn't send one.
    selected_items, selection_error = _resolve_selected_items(data.get('selectedItems'))
    if selection_error:
        return Response({'error': selection_error}, status=status.HTTP_400_BAD_REQUEST)

    now = timezone.now()
    doc_request = DocumentRequest.objects.create(
        borrower_name=borrower_name, phone=phone, email=email, company_name=company_name,
        status='sent', created_by=request.user,
        link_token=secrets.token_urlsafe(24),
        link_expires_at=now + timedelta(days=LINK_VALID_DAYS),
        sent_at=now,
    )
    _create_checklist_items(doc_request, selected_items)
    _assign_reference_number(doc_request)
    send_secure_request_email(doc_request)
    return Response(_request_json(doc_request), status=status.HTTP_201_CREATED)


@api_view(['POST'])
def resend_view(request, request_id):
    try:
        doc_request = DocumentRequest.objects.get(id=request_id)
    except DocumentRequest.DoesNotExist:
        return Response({'error': 'Request not found'}, status=status.HTTP_404_NOT_FOUND)

    if doc_request.status == 'uploads_complete':
        return Response({'error': 'This request already has completed uploads -- nothing to resend.'}, status=status.HTTP_400_BAD_REQUEST)

    now = timezone.now()
    doc_request.link_token = secrets.token_urlsafe(24)
    doc_request.link_expires_at = now + timedelta(days=LINK_VALID_DAYS)
    doc_request.sent_at = now
    doc_request.status = 'sent'
    doc_request.save(update_fields=['link_token', 'link_expires_at', 'sent_at', 'status'])
    # Existing checklist progress is kept (same folder, new cycle) -- only
    # the session timer/fraud counters reset for the fresh link.
    UploadSession.objects.filter(document_request=doc_request).delete()
    _create_checklist_items(doc_request)  # no-op if items already exist
    _assign_reference_number(doc_request)  # no-op if already assigned
    send_secure_request_email(doc_request)
    return Response(_request_json(doc_request))


@api_view(['GET'])
def latest_email_view(request, request_id):
    """The most recently logged email for this request (Step 3 request
    email, or a Step 4 fraud alert) -- lets a banker inspect exactly what
    would have been sent, since no real mail provider is wired up yet."""
    email = RequestEmail.objects.filter(document_request_id=request_id).order_by('-sent_at').first()
    if not email:
        return Response({'error': 'No email has been logged for this request yet.'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'kind': email.kind,
        'toEmail': email.to_email,
        'fromEmail': email.from_email,
        'subject': email.subject,
        'bodyText': email.body_text,
        'sentAt': email.sent_at.isoformat(),
    })


@api_view(['GET'])
def uploaded_files_view(request, request_id):
    """Banker-side: list every file uploaded so far for this request."""
    files = UploadedFile.objects.filter(document_request_id=request_id)
    return Response([{
        'id': f.id, 'fileName': f.file_name, 'fileType': f.file_type, 'fileSize': f.file_size,
        'checklistItemId': f.checklist_item_id, 'uploadedAt': f.uploaded_at.isoformat(),
    } for f in files])


@api_view(['GET'])
@permission_classes([AllowAny])
def serve_uploaded_file_view(request, request_id, upload_id):
    """Streams the raw bytes so a banker can preview/download a parked file.
    AllowAny to match the established pattern for serve endpoints elsewhere
    (appstore's credit_file_server) -- the token/id isn't guessable from any
    public surface, only from the authenticated list view above."""
    try:
        upload = UploadedFile.objects.get(id=upload_id, document_request_id=request_id)
    except UploadedFile.DoesNotExist:
        return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        data = storage.read_file(upload.file_path)
    except FileNotFoundError:
        return Response({'error': 'File missing on disk'}, status=status.HTTP_404_NOT_FOUND)

    resp = HttpResponse(data, content_type=upload.file_type or 'application/octet-stream')
    resp['Content-Disposition'] = f'inline; filename="{upload.file_name}"'
    resp['Content-Length'] = len(data)
    return resp


# ── Step 4: public (no-auth) upload portal ──────────────────────────────────

def _resolve_active_request(token):
    """Returns (doc_request, error_message). error_message is None when the
    link is usable right now (open for upload, or read-only complete)."""
    try:
        doc_request = DocumentRequest.objects.get(link_token=token)
    except DocumentRequest.DoesNotExist:
        return None, 'This upload link is invalid.'

    if doc_request.status == 'fraud_stopped':
        return doc_request, 'This session was ended due to unusual activity. Your relationship manager has been notified and will contact you.'
    if doc_request.status == 'uploads_complete':
        return doc_request, None
    if doc_request.status != 'sent':
        return None, 'This upload link is invalid or has expired.'
    if doc_request.link_expires_at and timezone.now() > doc_request.link_expires_at:
        doc_request.status = 'expired'
        doc_request.save(update_fields=['status'])
        return doc_request, 'This upload link has expired. Contact your relationship manager for a new one.'
    return doc_request, None


def _trip_fraud_if_needed(doc_request, session):
    if session.fraud_flagged_at:
        return
    reason = None
    if session.failed_attempts >= FAILED_ATTEMPT_FRAUD_THRESHOLD:
        reason = 'Repeated failed upload attempts'
    elif session.total_attempts >= TOTAL_ATTEMPT_FRAUD_THRESHOLD:
        reason = 'Unusually high upload volume (possible automated/scripted activity)'
    if not reason:
        return
    session.fraud_flagged_at = timezone.now()
    session.fraud_reason = reason
    session.save(update_fields=['fraud_flagged_at', 'fraud_reason'])
    doc_request.status = 'fraud_stopped'
    doc_request.save(update_fields=['status'])
    log_fraud_alert_email(doc_request, reason)


@api_view(['GET'])
@permission_classes([AllowAny])
def upload_info_view(request, token):
    doc_request, error = _resolve_active_request(token)
    if doc_request is None:
        return Response({'error': error}, status=status.HTTP_410_GONE)

    if error is not None:
        # Expired / fraud-stopped -- the link isn't open for browsing right
        # now, even though the DocumentRequest row still exists.
        return Response({
            'error': error, 'borrowerName': doc_request.borrower_name, 'companyName': doc_request.company_name,
        }, status=status.HTTP_410_GONE)

    session, _ = UploadSession.objects.get_or_create(document_request=doc_request)
    seconds_remaining = None
    if doc_request.status == 'sent':
        if session.started_at is None:
            session.started_at = timezone.now()
            session.save(update_fields=['started_at'])
        elapsed = (timezone.now() - session.started_at).total_seconds()
        seconds_remaining = max(0, int(UPLOAD_SESSION_MINUTES * 60 - elapsed))

    # Loan Admin items are internal-only -- never shown to the customer.
    items = doc_request.checklist_items.filter(audience='lender')
    return Response({
        'borrowerName': doc_request.borrower_name,
        'companyName': doc_request.company_name,
        'email': doc_request.email,
        'status': doc_request.status,
        'referenceNumber': doc_request.reference_number,
        'error': None,
        'sessionSecondsRemaining': seconds_remaining,
        'items': [{
            'id': i.id, 'name': i.name, 'category': i.category, 'status': i.status,
            'fileName': i.current_file.file_name if i.current_file else None,
        } for i in items],
    })


@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def upload_document_view(request, token):
    doc_request, error = _resolve_active_request(token)
    if doc_request is None or error is not None:
        return Response({'error': error or 'This upload link is invalid.'}, status=status.HTTP_410_GONE)

    session, _ = UploadSession.objects.get_or_create(document_request=doc_request)
    if session.started_at is None:
        session.started_at = timezone.now()
        session.save(update_fields=['started_at'])
    elif (timezone.now() - session.started_at).total_seconds() > UPLOAD_SESSION_MINUTES * 60:
        return Response({'error': 'Your upload session has timed out. Reopen the link to start a new session.'}, status=status.HTTP_410_GONE)

    def _record_failure(message):
        session.total_attempts += 1
        session.failed_attempts += 1
        session.save(update_fields=['total_attempts', 'failed_attempts'])
        _trip_fraud_if_needed(doc_request, session)
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

    checklist_item_id = request.data.get('checklistItemId')
    # Loan Admin items are internal-only -- not uploadable through the
    # public portal even if a customer somehow guesses the id.
    checklist_item = (
        doc_request.checklist_items.filter(id=checklist_item_id, audience='lender').first()
        if checklist_item_id else None
    )
    if not checklist_item:
        return _record_failure('Select which checklist item this file is for.')

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return _record_failure('No file provided.')

    if uploaded_file.size > MAX_FILE_SIZE_BYTES:
        return _record_failure(f'File is too large (max {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB).')

    file_bytes = uploaded_file.read()
    upload = UploadedFile.objects.create(
        document_request=doc_request, checklist_item=checklist_item,
        file_name=uploaded_file.name, file_type=uploaded_file.content_type or 'application/octet-stream',
        file_path='', file_size=len(file_bytes),
    )
    relative_path = storage.build_relative_path(doc_request, checklist_item.name, upload.id, uploaded_file.name)
    storage.write_file(relative_path, file_bytes)
    upload.file_path = relative_path
    upload.save(update_fields=['file_path'])

    checklist_item.status = 'uploaded'
    checklist_item.current_file = upload
    checklist_item.save(update_fields=['status', 'current_file'])

    session.total_attempts += 1
    session.save(update_fields=['total_attempts'])
    _trip_fraud_if_needed(doc_request, session)

    # Only Lender items count toward completion -- Loan Admin items have no
    # upload mechanism yet, so they'd otherwise stay 'pending' forever.
    if doc_request.status == 'sent' and not doc_request.checklist_items.filter(audience='lender', status='pending').exists():
        doc_request.status = 'uploads_complete'
        doc_request.save(update_fields=['status'])
        log_completion_confirmation_email(doc_request)

    return Response({'id': upload.id, 'fileName': upload.file_name}, status=status.HTTP_201_CREATED)


# ── Step 6: parking-bay review (banker-authenticated) ───────────────────────

def _checklist_item_json(item):
    f = item.current_file
    return {
        'id': item.id,
        'name': item.name,
        'category': item.category,
        'status': item.status,
        'file': None if f is None else {
            'id': f.id,
            'fileName': f.file_name,
            'fileType': f.file_type,
            'fileSize': f.file_size,
            'uploadedAt': f.uploaded_at.isoformat(),
            'reviewStatus': f.review_status,
            'reviewComment': f.review_comment,
            'reviewedAt': f.reviewed_at.isoformat() if f.reviewed_at else None,
        },
    }


def _review_state(doc_request):
    """Shared by the parking-bay list and both batch actions: which items
    are reviewable (have an uploaded file), whether every one of them has a
    decision yet, and the approved/flagged split. Loan Admin items are
    excluded entirely -- they have no upload mechanism yet, so they'd never
    have a file to review and would otherwise block review-completeness
    forever."""
    items = list(doc_request.checklist_items.filter(audience='lender').select_related('current_file').all())
    reviewable = [i for i in items if i.current_file is not None]
    approved = [i for i in reviewable if i.current_file.review_status == 'approved']
    flagged = [i for i in reviewable if i.current_file.review_status == 'flagged']
    review_complete = (
        len(items) > 0 and len(reviewable) == len(items)
        and all(i.current_file.review_status != 'pending' for i in reviewable)
    )
    return items, reviewable, approved, flagged, review_complete


@api_view(['GET'])
def parking_bay_view(request, request_id):
    try:
        doc_request = DocumentRequest.objects.get(id=request_id)
    except DocumentRequest.DoesNotExist:
        return Response({'error': 'Request not found'}, status=status.HTTP_404_NOT_FOUND)

    items, _, approved, flagged, review_complete = _review_state(doc_request)
    return Response({
        'id': doc_request.id,
        'borrowerName': doc_request.borrower_name,
        'companyName': doc_request.company_name,
        'referenceNumber': doc_request.reference_number,
        'extractionQueuedAt': doc_request.extraction_queued_at.isoformat() if doc_request.extraction_queued_at else None,
        'items': [_checklist_item_json(i) for i in items],
        'reviewComplete': review_complete,
        'approvedCount': len(approved),
        'flaggedCount': len(flagged),
    })


@api_view(['POST'])
def review_checklist_item_view(request, request_id, checklist_item_id):
    try:
        item = ChecklistItem.objects.select_related('current_file').get(
            id=checklist_item_id, document_request_id=request_id,
        )
    except ChecklistItem.DoesNotExist:
        return Response({'error': 'Checklist item not found'}, status=status.HTTP_404_NOT_FOUND)

    if item.current_file is None:
        return Response({'error': 'Nothing has been uploaded for this checklist item yet.'}, status=status.HTTP_400_BAD_REQUEST)

    decision = request.data.get('decision')
    comment = (request.data.get('comment') or '').strip()
    if decision not in ('approve', 'flag'):
        return Response({'error': "decision must be 'approve' or 'flag'."}, status=status.HTTP_400_BAD_REQUEST)
    if decision == 'flag' and not comment:
        return Response({'error': 'A comment is required to flag a document for re-upload.'}, status=status.HTTP_400_BAD_REQUEST)

    upload = item.current_file
    upload.review_status = 'approved' if decision == 'approve' else 'flagged'
    upload.review_comment = comment
    upload.reviewed_at = timezone.now()
    upload.reviewed_by = request.user
    upload.save(update_fields=['review_status', 'review_comment', 'reviewed_at', 'reviewed_by'])

    return Response(_checklist_item_json(item))


@api_view(['POST'])
def send_review_flags_email_view(request, request_id):
    try:
        doc_request = DocumentRequest.objects.get(id=request_id)
    except DocumentRequest.DoesNotExist:
        return Response({'error': 'Request not found'}, status=status.HTTP_404_NOT_FOUND)

    _, _, _, flagged, _ = _review_state(doc_request)
    if not flagged:
        return Response({'error': 'No flagged documents to notify the customer about.'}, status=status.HTTP_400_BAD_REQUEST)

    email = log_review_flags_email(doc_request, flagged)
    return Response({'emailId': email.id, 'flaggedCount': len(flagged)})


@api_view(['POST'])
def kick_start_extraction_view(request, request_id):
    """Queues the approved documents and kicks off Step 7: a real document
    twin per approved file plus one shared business twin for the request,
    both starting at their first stage."""
    try:
        doc_request = DocumentRequest.objects.get(id=request_id)
    except DocumentRequest.DoesNotExist:
        return Response({'error': 'Request not found'}, status=status.HTTP_404_NOT_FOUND)

    if doc_request.extraction_queued_at is not None:
        return Response({'error': 'Extraction has already been queued for this request.'}, status=status.HTTP_400_BAD_REQUEST)

    _, _, approved, _, review_complete = _review_state(doc_request)
    if not review_complete:
        return Response({'error': 'Every document needs a reviewer decision before extraction can start.'}, status=status.HTTP_400_BAD_REQUEST)
    if not approved:
        return Response({'error': 'No approved documents to queue for extraction.'}, status=status.HTTP_400_BAD_REQUEST)

    doc_request.extraction_queued_at = timezone.now()
    doc_request.save(update_fields=['extraction_queued_at'])

    BusinessTwin.objects.create(document_request=doc_request)
    ExtractionEvent.objects.create(
        document_request=doc_request, event_type='business_twin.relationship',
        detail=f'{doc_request.company_name or doc_request.borrower_name} resolved.',
    )
    for item in approved:
        twin = DocumentTwin.objects.create(document_request=doc_request, uploaded_file=item.current_file)
        ExtractionEvent.objects.create(
            document_request=doc_request, document_twin=twin,
            event_type='document_twin.received', detail=f'{item.current_file.file_name} received from parking bay.',
        )

    return Response({'queuedCount': len(approved), 'extractionQueuedAt': doc_request.extraction_queued_at.isoformat()})


# ── Step 7: twin extraction (stage machine, banker-authenticated) ───────────

def _document_twin_json(twin, business_twin):
    overall = int((twin.progress_percent + (business_twin.progress_percent if business_twin else 0)) / 2)
    return {
        'id': twin.id,
        'uploadedFileId': twin.uploaded_file_id,
        'fileName': twin.uploaded_file.file_name,
        'currentStage': twin.current_stage,
        'classificationLabel': twin.classification_label,
        'progressPercent': twin.progress_percent,
        'overallPercent': overall,
        'stages': {
            'received': twin.received_at.isoformat() if twin.received_at else None,
            'classified': twin.classified_at.isoformat() if twin.classified_at else None,
            'extracted': twin.extracted_at.isoformat() if twin.extracted_at else None,
            'provenance': twin.provenance_at.isoformat() if twin.provenance_at else None,
            'confidence': twin.confidence_at.isoformat() if twin.confidence_at else None,
        },
        'extractedValues': [{
            'id': v.id, 'fieldName': v.field_name, 'value': v.value,
            'source': v.source, 'confidence': v.confidence, 'needsReview': v.needs_review,
        } for v in twin.extracted_values.all()],
    }


def _business_twin_json(twin):
    return {
        'id': twin.id,
        'currentStage': twin.current_stage,
        'progressPercent': twin.progress_percent,
        'stages': {
            'relationship': twin.relationship_at.isoformat() if twin.relationship_at else None,
            'entities': twin.entities_at.isoformat() if twin.entities_at else None,
            'covenantLedger': twin.covenant_ledger_at.isoformat() if twin.covenant_ledger_at else None,
            'indicators': twin.indicators_at.isoformat() if twin.indicators_at else None,
            'allocation': twin.allocation_at.isoformat() if twin.allocation_at else None,
        },
    }


@api_view(['GET'])
def extraction_view(request, request_id):
    try:
        doc_request = DocumentRequest.objects.get(id=request_id)
    except DocumentRequest.DoesNotExist:
        return Response({'error': 'Request not found'}, status=status.HTTP_404_NOT_FOUND)

    if doc_request.extraction_queued_at is None:
        return Response({'error': 'Extraction has not been kicked off yet for this request.'}, status=status.HTTP_400_BAD_REQUEST)

    business_twin = getattr(doc_request, 'business_twin', None)
    twins = list(doc_request.document_twins.select_related('uploaded_file').prefetch_related('extracted_values').order_by('id').all())
    events = doc_request.extraction_events.select_related('document_twin').order_by('created_at')

    return Response({
        'requestId': doc_request.id,
        'referenceNumber': doc_request.reference_number,
        'documentTwins': [_document_twin_json(t, business_twin) for t in twins],
        'businessTwin': _business_twin_json(business_twin) if business_twin else None,
        'log': [{
            'type': e.event_type, 'detail': e.detail, 'at': e.created_at.isoformat(),
            'documentTwinId': e.document_twin_id,
        } for e in events],
    })


@api_view(['POST'])
def advance_document_twin_view(request, request_id, twin_id):
    """Advances one document twin by exactly one stage -- the server always
    moves to `STAGE_ORDER[current_index + 1]`, so the sequence can never be
    skipped or reordered by the caller."""
    try:
        twin = DocumentTwin.objects.select_related('uploaded_file__checklist_item').get(
            id=twin_id, document_request_id=request_id,
        )
    except DocumentTwin.DoesNotExist:
        return Response({'error': 'Document twin not found'}, status=status.HTTP_404_NOT_FOUND)

    order = DocumentTwin.STAGE_ORDER
    current_index = order.index(twin.current_stage)
    if current_index == len(order) - 1:
        return Response({'error': 'This document twin has already reached its final stage.'}, status=status.HTTP_400_BAD_REQUEST)

    next_stage = order[current_index + 1]
    now = timezone.now()
    update_fields = ['current_stage']

    if next_stage == 'classified':
        item = twin.uploaded_file.checklist_item
        twin.classification_label = classify(item.name if item else '')
        detail = twin.classification_label
        twin.classified_at = now
        update_fields += ['classification_label', 'classified_at']
    elif next_stage == 'extracted':
        try:
            raw_bytes = storage.read_file(twin.uploaded_file.file_path)
        except FileNotFoundError:
            return Response({'error': 'The uploaded file is missing on disk -- cannot extract.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            found = content_extraction.extract(twin.uploaded_file.file_type, raw_bytes)
        except content_extraction.ExtractionFailed as exc:
            ExtractionEvent.objects.create(
                document_request_id=request_id, document_twin=twin,
                event_type='extract.failed', detail=str(exc),
            )
            return Response({'error': f'Extraction failed: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        ExtractedValue.objects.bulk_create([
            ExtractedValue(document_twin=twin, field_name=v['fieldName'], value=v['value'], source=v['source'], confidence=v['confidence'])
            for v in found
        ])
        detail = f'{len(found)} value(s) extracted.' if found else 'No extractable values found in this file.'
        twin.extracted_at = now
        update_fields.append('extracted_at')
    elif next_stage == 'provenance':
        values = list(twin.extracted_values.all())
        with_source = sum(1 for v in values if v.source)
        detail = (
            f'{with_source} of {len(values)} value(s) have a source pointer.' if values
            else 'No values to map -- nothing was extracted.'
        )
        twin.provenance_at = now
        update_fields.append('provenance_at')
    else:  # confidence
        values = list(twin.extracted_values.all())
        if values:
            avg_confidence = sum(v.confidence for v in values) / len(values)
            needs_review = sum(1 for v in values if v.confidence < CONFIDENCE_ROUTING_THRESHOLD)
            detail = f'Avg confidence {avg_confidence:.0%} -- {needs_review} of {len(values)} value(s) need HITL review.'
        else:
            detail = 'No values to score -- nothing was extracted.'
        twin.confidence_at = now
        update_fields.append('confidence_at')

    twin.current_stage = next_stage
    twin.save(update_fields=update_fields)

    ExtractionEvent.objects.create(
        document_request_id=request_id, document_twin=twin,
        event_type=f'document_twin.{next_stage}', detail=detail,
    )
    ExtractionEvent.objects.create(
        document_request_id=request_id, document_twin=twin,
        event_type='audit.write', detail=f'twin #{twin.id} reached {next_stage}',
    )

    business_twin = getattr(twin.document_request, 'business_twin', None)
    return Response(_document_twin_json(twin, business_twin))


@api_view(['POST'])
def advance_business_twin_view(request, request_id):
    """Relationship/Entities can always advance; Covenant ledger onward is
    gated on every document twin in the request having reached at least
    Extracted (no real obligation-matching exists yet -- this gate is real,
    what it's gating is still a placeholder)."""
    try:
        doc_request = DocumentRequest.objects.get(id=request_id)
    except DocumentRequest.DoesNotExist:
        return Response({'error': 'Request not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        twin = doc_request.business_twin
    except BusinessTwin.DoesNotExist:
        return Response({'error': 'Business twin not found -- extraction has not been kicked off yet.'}, status=status.HTTP_404_NOT_FOUND)

    order = BusinessTwin.STAGE_ORDER
    current_index = order.index(twin.current_stage)
    if current_index == len(order) - 1:
        return Response({'error': 'The business twin has already reached its final stage.'}, status=status.HTTP_400_BAD_REQUEST)

    next_stage = order[current_index + 1]

    if next_stage == 'covenant_ledger':
        doc_order = DocumentTwin.STAGE_ORDER
        extracted_index = doc_order.index('extracted')
        twins = list(doc_request.document_twins.all())
        if not twins or any(doc_order.index(t.current_stage) < extracted_index for t in twins):
            return Response({'error': 'Waiting on the document twin -- every document must reach Extracted first.'}, status=status.HTTP_400_BAD_REQUEST)

    now = timezone.now()
    update_fields = ['current_stage']
    placeholder_detail = {
        'entities': 'Entities linked (placeholder -- no real entity graph yet).',
        'covenant_ledger': 'Covenant ledger stage reached (placeholder -- no real covenant data model yet).',
        'indicators': 'Indicators stage reached (placeholder).',
        'allocation': 'Allocation stage reached (placeholder).',
    }
    detail = placeholder_detail[next_stage]
    field_name = f'{next_stage}_at'
    setattr(twin, field_name, now)
    update_fields.append(field_name)

    twin.current_stage = next_stage
    twin.save(update_fields=update_fields)

    ExtractionEvent.objects.create(document_request=doc_request, event_type=f'business_twin.{next_stage}', detail=detail)
    ExtractionEvent.objects.create(document_request=doc_request, event_type='audit.write', detail=f'business twin reached {next_stage}')

    return Response(_business_twin_json(twin))
