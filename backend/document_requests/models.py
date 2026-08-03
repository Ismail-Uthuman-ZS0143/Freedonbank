from django.conf import settings
from django.db import models


class DocumentRequest(models.Model):
    """Step 2 of the flow: a banker's request for a borrower to upload a
    checklist of documents. `link_token`/`link_expires_at` back the
    single-purpose secure upload link (Step 4 -- the actual upload portal --
    isn't built yet, so the link doesn't resolve to anything real yet)."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent · link active'),
        ('uploads_complete', 'Uploads complete'),
        ('expired', 'Link expired · no upload'),
        ('fraud_stopped', 'Session ended — fraud guard'),
    ]

    borrower_name = models.TextField()
    phone = models.TextField(blank=True, default='')
    email = models.TextField(blank=True, default='')
    company_name = models.TextField(blank=True, default='')

    status = models.TextField(choices=STATUS_CHOICES, default='draft')
    link_token = models.CharField(max_length=48, unique=True, null=True, blank=True)
    link_expires_at = models.DateTimeField(null=True, blank=True)
    # Customer-facing case reference (Step 5's "Reference REQ-2026-0847"),
    # e.g. shown on the completion screen and in the confirmation email.
    # Assigned once at first send and kept stable across resends -- unlike
    # link_token, which rotates each time.
    reference_number = models.CharField(max_length=32, unique=True, null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='document_requests'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    # Step 6's "Kick-start extraction" button -- Step 7 (the actual twin
    # extraction pipeline) isn't built yet, so this just marks the moment
    # the reviewer queued the approved documents; nothing consumes it yet.
    extraction_queued_at = models.DateTimeField(null=True, blank=True)
    # Step 8's "Submit for loan officer review" -- set once, real gate is
    # every ExtractedValue across every DocumentTwin in the request being
    # at/above CONFIDENCE_ROUTING_THRESHOLD (see views.py). No real
    # loan-officer queue/handoff destination exists past this point yet --
    # this just marks the moment the reviewer packaged the request.
    submitted_for_review_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'document_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.borrower_name} · {self.company_name} ({self.status})'


class RequestEmail(models.Model):
    """Step 3's secure request email, Step 4's fraud alert, Step 5's
    completion confirmation, and Step 6's review-flags re-request all log
    here as an append-only audit row -- inspectable via the admin or the
    API regardless of delivery outcome. `delivered` tracks whether
    document_requests/mail_delivery.py's real direct-to-MX send actually
    succeeded; this row is created either way, so a delivery failure is
    never silently invisible."""
    KIND_CHOICES = [
        ('request', 'Secure document request'),
        ('fraud_alert', 'Fraud/session-guard alert'),
        ('confirmation', 'Upload completion confirmation'),
        ('review_flags', 'Batched flagged-document re-request'),
        ('discrepancy', 'Step 8 HITL discrepancy — customer query'),
    ]

    document_request = models.ForeignKey(DocumentRequest, on_delete=models.CASCADE, related_name='emails')
    kind = models.TextField(choices=KIND_CHOICES, default='request')
    to_email = models.TextField()
    from_email = models.TextField(default='requests@freedombankva.com')
    subject = models.TextField()
    body_text = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    delivery_attempted = models.BooleanField(default=False)
    delivered = models.BooleanField(default=False)

    class Meta:
        db_table = 'request_emails'
        ordering = ['-sent_at']

    def __str__(self):
        return f'{self.subject} -> {self.to_email} ({self.sent_at:%Y-%m-%d %H:%M})'


class UploadedFile(models.Model):
    """A customer-uploaded document, sitting in the 'parking bay' until a
    banker reviews it (Step 6). Review fields live here, not on
    ChecklistItem, so a re-upload after a flag naturally starts a fresh
    'pending' review on the new row while the old flagged row (and its
    comment) stays in history untouched."""
    REVIEW_STATUS_CHOICES = [
        ('pending', 'Pending review'),
        ('approved', 'Ready for extraction'),
        ('flagged', 'Flagged — re-upload'),
    ]

    document_request = models.ForeignKey(DocumentRequest, on_delete=models.CASCADE, related_name='uploaded_files')
    checklist_item = models.ForeignKey(
        'ChecklistItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='files'
    )
    file_name = models.TextField()
    file_type = models.TextField()
    file_path = models.TextField(help_text='Path relative to settings.UPLOAD_STORAGE_ROOT')
    file_size = models.IntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    review_status = models.TextField(choices=REVIEW_STATUS_CHOICES, default='pending')
    review_comment = models.TextField(blank=True, default='')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )

    class Meta:
        db_table = 'uploaded_files'
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.file_name


class ChecklistItem(models.Model):
    """One row of a request's checklist, instantiated at send time from
    whichever items the banker selected in Step 2b's customize picker
    (`checklist.py`'s CHECKLIST_TEMPLATE) so Step 4 can track upload status
    per document.

    `audience` is the mockup's Lender vs. Loan Admin split: only 'lender'
    items are ever shown to the customer (Step 3 email, Step 4 upload
    portal) or counted toward "uploads complete" -- 'loan_admin' items are
    tracked here for real (visible on the banker's side) but have **no
    upload mechanism built yet**, an explicit, documented gap rather than a
    silently-broken feature."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('uploaded', 'Uploaded'),
    ]
    AUDIENCE_CHOICES = [
        ('lender', 'Lender · customer-facing'),
        ('loan_admin', 'Loan Admin · internal'),
    ]

    document_request = models.ForeignKey(DocumentRequest, on_delete=models.CASCADE, related_name='checklist_items')
    name = models.TextField()
    category = models.TextField(blank=True, default='')
    audience = models.TextField(choices=AUDIENCE_CHOICES, default='lender')
    order = models.IntegerField(default=0)
    status = models.TextField(choices=STATUS_CHOICES, default='pending')
    # Most recent file for this item -- a re-upload replaces this pointer
    # rather than the checklist showing duplicate rows; the superseded
    # UploadedFile row (and its file on disk) is kept, not deleted.
    current_file = models.ForeignKey(
        UploadedFile, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )

    class Meta:
        db_table = 'checklist_items'
        ordering = ['order']

    def __str__(self):
        return self.name


class UploadSession(models.Model):
    """Step 4's session timer + the (honestly-scoped) fraud/session guard.

    `started_at` is set the first time the customer opens the upload link
    (not when the banker sends it). `total_attempts`/`failed_attempts` back
    two simple, deterministic heuristics -- NOT real bot/geo detection:
      - failed_attempts >= threshold  -> "repeated failed upload attempts"
      - total_attempts  >= threshold  -> "unusually high upload volume"
    Location-jump detection from the mockup copy is NOT implemented here --
    it would need real IP geolocation infrastructure this project doesn't have.
    """
    document_request = models.OneToOneField(DocumentRequest, on_delete=models.CASCADE, related_name='upload_session')
    started_at = models.DateTimeField(null=True, blank=True)
    total_attempts = models.IntegerField(default=0)
    failed_attempts = models.IntegerField(default=0)
    fraud_flagged_at = models.DateTimeField(null=True, blank=True)
    fraud_reason = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'upload_sessions'

    def __str__(self):
        return f'Session for request #{self.document_request_id}'


class DocumentTwin(models.Model):
    """Step 7's document-twin stage machine -- Received -> Classified ->
    Extracted -> Provenance -> Confidence. This is a real, DB-backed
    progression (one stage at a time, via an explicit trigger -- never
    skippable since the server always advances by exactly one).
    'Classified' uses a deterministic lookup by checklist item name (see
    extraction.py), not file content. 'Extracted' runs real content
    extraction (see content_extraction.py) over the actual uploaded bytes --
    regex matches over genuinely-extracted text, or direct cell reads for
    spreadsheets -- producing real ExtractedValue rows with real confidence
    scores; there is still no real NLP/AI, just honest pattern-matching."""
    STAGE_CHOICES = [
        ('received', 'Received'),
        ('classified', 'Classified'),
        ('extracted', 'Extracted'),
        ('provenance', 'Provenance'),
        ('confidence', 'Confidence'),
    ]
    STAGE_ORDER = ['received', 'classified', 'extracted', 'provenance', 'confidence']

    document_request = models.ForeignKey(DocumentRequest, on_delete=models.CASCADE, related_name='document_twins')
    uploaded_file = models.OneToOneField(UploadedFile, on_delete=models.CASCADE, related_name='twin')
    current_stage = models.TextField(choices=STAGE_CHOICES, default='received')
    classification_label = models.TextField(blank=True, default='')

    received_at = models.DateTimeField(auto_now_add=True)
    classified_at = models.DateTimeField(null=True, blank=True)
    extracted_at = models.DateTimeField(null=True, blank=True)
    provenance_at = models.DateTimeField(null=True, blank=True)
    confidence_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'document_twins'

    def __str__(self):
        return f'Twin for {self.uploaded_file.file_name} ({self.current_stage})'

    @property
    def completed_stage_count(self):
        return self.STAGE_ORDER.index(self.current_stage) + 1

    @property
    def progress_percent(self):
        return int(self.completed_stage_count / len(self.STAGE_ORDER) * 100)


CONFIDENCE_ROUTING_THRESHOLD = 0.85  # below this, a value needs HITL review (Step 8)


class ExtractedValue(models.Model):
    """A real value pulled from a document twin's actual file content at its
    'Extracted' stage (see content_extraction.py) -- regex match over
    genuinely-extracted text, or a direct spreadsheet cell read. `source`
    and `confidence` are both real: a page/line/cell pointer and a
    deterministic heuristic score, not fabricated provenance/ML output."""
    document_twin = models.ForeignKey(DocumentTwin, on_delete=models.CASCADE, related_name='extracted_values')
    field_name = models.TextField()
    value = models.TextField()
    source = models.TextField(blank=True, default='')
    confidence = models.FloatField()

    class Meta:
        db_table = 'extracted_values'
        ordering = ['id']

    def __str__(self):
        return f'{self.field_name}={self.value} ({self.confidence:.0%})'

    @property
    def needs_review(self):
        return self.confidence < CONFIDENCE_ROUTING_THRESHOLD


class BusinessTwin(models.Model):
    """Step 7's business-twin stage machine for the relationship behind one
    DocumentRequest -- Relationship/Entities can start immediately, but
    Covenant ledger/Indicators/Allocation are gated on every document twin in
    the request having reached at least 'extracted' (enforced in views.py).
    No real covenant/entity data model exists yet -- this only tracks honest
    stage progression, not real obligation matching."""
    STAGE_CHOICES = [
        ('relationship', 'Relationship'),
        ('entities', 'Entities'),
        ('covenant_ledger', 'Covenant ledger'),
        ('indicators', 'Indicators'),
        ('allocation', 'Allocation'),
    ]
    STAGE_ORDER = ['relationship', 'entities', 'covenant_ledger', 'indicators', 'allocation']

    document_request = models.OneToOneField(DocumentRequest, on_delete=models.CASCADE, related_name='business_twin')
    current_stage = models.TextField(choices=STAGE_CHOICES, default='relationship')

    relationship_at = models.DateTimeField(auto_now_add=True)
    entities_at = models.DateTimeField(null=True, blank=True)
    covenant_ledger_at = models.DateTimeField(null=True, blank=True)
    indicators_at = models.DateTimeField(null=True, blank=True)
    allocation_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'business_twins'

    def __str__(self):
        return f'Business twin for request #{self.document_request_id} ({self.current_stage})'

    @property
    def completed_stage_count(self):
        return self.STAGE_ORDER.index(self.current_stage) + 1

    @property
    def progress_percent(self):
        return int(self.completed_stage_count / len(self.STAGE_ORDER) * 100)


class ExtractionEvent(models.Model):
    """Append-only live log for Step 7 (one row per stage transition, plus a
    matching 'audit.write' row) -- same audit pattern as LoginEvent/
    RequestEmail, no add/change permission in admin."""
    document_request = models.ForeignKey(DocumentRequest, on_delete=models.CASCADE, related_name='extraction_events')
    document_twin = models.ForeignKey(
        DocumentTwin, on_delete=models.CASCADE, null=True, blank=True, related_name='events'
    )
    event_type = models.TextField()
    detail = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'extraction_events'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.event_type} ({self.created_at:%H:%M:%S})'


class ChecklistPreference(models.Model):
    """Step 2b (v5) -- a banker's saved default checklist, configured once
    under Profile settings -> Document checklist rather than rebuilt on
    every request. `selected_items` is a JSON list of {category, name}
    objects; audience is always re-resolved from checklist.CHECKLIST_TEMPLATE
    at send time (see views.py), never trusted from what's stored here."""
    banker = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='checklist_preference')
    selected_items = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'checklist_preferences'

    def __str__(self):
        return f'Checklist preference for {self.banker}'
