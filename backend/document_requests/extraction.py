"""Step 7's deterministic classification lookup -- keyed by checklist item
name, not file content. There is no real OCR/AI extraction pipeline in this
project (an explicit scope decision); this only provides a stable, honest
label per document type so the document twin's 'Classified' stage has
something real (if simple) to show. Covers the full v3 checklist master
template (checklist.py's CHECKLIST_TEMPLATE) -- any item not listed here
(e.g. a name that predates that template) falls back to 'Unclassified
document' rather than guessing.
"""

CLASSIFICATION_BY_ITEM_NAME = {
    'Corporate Resolution': 'Corporate resolution',
    'Certificate of Good Standing': 'Certificate of good standing',
    'Articles of Incorporation / Certified Bylaws': 'Formation document',
    'Operating Agreement (LLC)': 'Formation document',
    'Certificate of Organization (LLC)': 'Formation document',
    'Certificate of Fact': 'Certificate of good standing',
    'Partnership Agreement': 'Formation document',
    'Certificate of Limited Partnership': 'Formation document',
    'Personal Financial Statements': 'Financial statement',
    'Personal Tax Returns': 'Tax return',
    'Corporate Financial Statements': 'Financial statement',
    'Corporate Tax Returns': 'Tax return',
    'Credit Bureau Report — Personal': 'Credit report',
    'Credit Bureau Report — Corporate': 'Credit report',
    'Identification Verification': 'Identification document',
    'OFAC Verification': 'Compliance verification',

    'Loan Presentation / Submission': 'Loan presentation',
    'Risk Rating Form': 'Risk rating form',
    "Borrower's Request for Financing / Loan Application Package": 'Loan application',

    'Commitment Letter': 'Commitment letter',
    "Lender's Letter of Instructions": 'Lender instructions',
    'DDA Account Information': 'Account information',

    'Deed of Trust Note': 'Security instrument',
    'Deed of Trust': 'Security instrument',
    'Assignment of Leases & Rents': 'Security instrument',
    'Guaranty Agreement': 'Guaranty agreement',
    'Indemnity Agreement (Hazardous Waste)': 'Indemnity agreement',
    'Security Agreement': 'Security instrument',
    'Subordination Agreement': 'Subordination agreement',
    'UCC Lien Search': 'Lien search',
    'Financing Statements (County/State)': 'Financing statement',

    'Title Policy': 'Title document',
    'Title Binder or Commitment': 'Title document',
    "Insured's Closing Letter": 'Title document',
    'Covenants, Restrictions & Easements': 'Title document',

    'Funding Sheets': 'Funding sheet',
    'Attorney Correspondence': 'Correspondence',

    'Appraisal Report': 'Appraisal report',
    'Property Description': 'Property description',
    'Appraisal Review Sheet': 'Appraisal report',
    'Flood Certification / Zone Location': 'Flood certification',
    'Fire Hazard Insurance': 'Insurance document',
    'Liability Insurance': 'Insurance document',
    "Workman's Compensation": 'Insurance document',

    'Recorded Plat of Survey': 'Survey',
    'Resubdivision Plat': 'Survey',
    'Site / House Plans': 'Site plan',
}


def classify(item_name):
    return CLASSIFICATION_BY_ITEM_NAME.get(item_name, 'Unclassified document')
