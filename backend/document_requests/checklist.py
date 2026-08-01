"""Step 2b's full checklist master template (from the v3 mockup's "Customize
& Send Secure Upload Link" modal) -- ~50 items across 8 categories, each
tagged 'lender' (customer-facing: appears in the Step 3 email and the Step 4
upload portal) or 'loan_admin' (internal-only: tracked as a ChecklistItem so
it shows up on the banker's side, but never shown to the customer and not
yet uploadable by the banker either -- that upload path isn't built in this
pass, a documented gap).

`selected` mirrors the exact pre-checked state shown in the v3 mockup's
modal for its example scenario (27 items: 12 Lender + 15 Loan Admin,
verified against the mockup's own "12 customer-facing · 16 internal" count,
which includes one demo-only custom item this project doesn't build support
for). It is NOT driven by any real loan-type/product rules -- none exist in
this project -- so it's an honest, fixed starting point every request's
picker opens with, not a computed recommendation. Custom item add/remove
(shown in the mockup) isn't built in this pass either -- banks pick from
this fixed template only.
"""

CATEGORIES = [
    'Organizational documents / financial info',
    'Initial loan documents',
    'Commitments for financing',
    'Security documents',
    'Title insurance',
    'Correspondence',
    'Appraisals',
    'Surveys',
]

LENDER = 'lender'
LOAN_ADMIN = 'loan_admin'

# (category, name, audience, selected-by-default)
CHECKLIST_TEMPLATE = [
    ('Organizational documents / financial info', 'Corporate Resolution', LENDER, True),
    ('Organizational documents / financial info', 'Certificate of Good Standing', LOAN_ADMIN, True),
    ('Organizational documents / financial info', 'Articles of Incorporation / Certified Bylaws', LENDER, True),
    ('Organizational documents / financial info', 'Operating Agreement (LLC)', LENDER, True),
    ('Organizational documents / financial info', 'Certificate of Organization (LLC)', LENDER, True),
    ('Organizational documents / financial info', 'Certificate of Fact', LOAN_ADMIN, False),
    ('Organizational documents / financial info', 'Partnership Agreement', LENDER, False),
    ('Organizational documents / financial info', 'Certificate of Limited Partnership', LENDER, False),
    ('Organizational documents / financial info', 'Personal Financial Statements', LENDER, True),
    ('Organizational documents / financial info', 'Personal Tax Returns', LENDER, True),
    ('Organizational documents / financial info', 'Corporate Financial Statements', LENDER, True),
    ('Organizational documents / financial info', 'Corporate Tax Returns', LENDER, True),
    ('Organizational documents / financial info', 'Credit Bureau Report — Personal', LOAN_ADMIN, True),
    ('Organizational documents / financial info', 'Credit Bureau Report — Corporate', LOAN_ADMIN, False),
    ('Organizational documents / financial info', 'Identification Verification', LOAN_ADMIN, True),
    ('Organizational documents / financial info', 'OFAC Verification', LOAN_ADMIN, True),

    ('Initial loan documents', 'Loan Presentation / Submission', LENDER, True),
    ('Initial loan documents', 'Risk Rating Form', LENDER, True),
    ('Initial loan documents', "Borrower's Request for Financing / Loan Application Package", LENDER, False),

    ('Commitments for financing', 'Commitment Letter', LENDER, True),
    ('Commitments for financing', "Lender's Letter of Instructions", LOAN_ADMIN, False),
    ('Commitments for financing', 'DDA Account Information', LENDER, False),

    ('Security documents', 'Deed of Trust Note', LOAN_ADMIN, True),
    ('Security documents', 'Deed of Trust', LOAN_ADMIN, True),
    ('Security documents', 'Assignment of Leases & Rents', LOAN_ADMIN, False),
    ('Security documents', 'Guaranty Agreement', LOAN_ADMIN, True),
    ('Security documents', 'Indemnity Agreement (Hazardous Waste)', LOAN_ADMIN, False),
    ('Security documents', 'Security Agreement', LOAN_ADMIN, False),
    ('Security documents', 'Subordination Agreement', LOAN_ADMIN, False),
    ('Security documents', 'UCC Lien Search', LOAN_ADMIN, False),
    ('Security documents', 'Financing Statements (County/State)', LOAN_ADMIN, False),

    ('Title insurance', 'Title Policy', LOAN_ADMIN, True),
    ('Title insurance', 'Title Binder or Commitment', LOAN_ADMIN, True),
    ('Title insurance', "Insured's Closing Letter", LOAN_ADMIN, True),
    ('Title insurance', 'Covenants, Restrictions & Easements', LOAN_ADMIN, False),

    ('Correspondence', 'Funding Sheets', LOAN_ADMIN, False),
    ('Correspondence', 'Attorney Correspondence', LOAN_ADMIN, False),

    ('Appraisals', 'Appraisal Report', LOAN_ADMIN, True),
    ('Appraisals', 'Property Description', LENDER, True),
    ('Appraisals', 'Appraisal Review Sheet', LOAN_ADMIN, True),
    ('Appraisals', 'Flood Certification / Zone Location', LOAN_ADMIN, True),
    ('Appraisals', 'Fire Hazard Insurance', LOAN_ADMIN, True),
    ('Appraisals', 'Liability Insurance', LOAN_ADMIN, True),
    ('Appraisals', "Workman's Compensation", LOAN_ADMIN, False),

    ('Surveys', 'Recorded Plat of Survey', LENDER, False),
    ('Surveys', 'Resubdivision Plat', LENDER, False),
    ('Surveys', 'Site / House Plans', LENDER, False),
]

_BY_KEY = {(category, name): audience for category, name, audience, _ in CHECKLIST_TEMPLATE}


def default_selection():
    """The template's own pre-checked items -- [(category, name, audience), ...]."""
    return [(category, name, audience) for category, name, audience, selected in CHECKLIST_TEMPLATE if selected]


def resolve_audience(category, name):
    """Looks up the authoritative audience for a (category, name) pair from
    the template -- the client only ever sends which items are checked, not
    their audience, so a request can't relabel an item Lender/Loan Admin by
    forging the request body."""
    return _BY_KEY.get((category, name))
