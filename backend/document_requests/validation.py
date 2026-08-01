"""Field validation for the Step 2 "new document request" form.

The mockup's copy claims things like "domain verified" and "matches state
registry" -- those need a real mail-verification service and a business
registry API, neither of which exist here. Rather than fake that, these
checks are honestly scoped to format validation only, with wording that
doesn't overclaim what was actually checked.
"""
import re

PHONE_DIGITS_RE = re.compile(r'\D')
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def validate_fields(borrower_name, phone, email, company_name):
    """Returns {field: {'ok': bool, 'message': str}} for all four fields."""
    results = {}

    borrower_name = (borrower_name or '').strip()
    if borrower_name:
        results['borrowerName'] = {'ok': True, 'message': 'Looks good'}
    else:
        results['borrowerName'] = {'ok': False, 'message': 'Borrower name is required'}

    phone = (phone or '').strip()
    digits = PHONE_DIGITS_RE.sub('', phone)
    if len(digits) == 10:
        results['phone'] = {'ok': True, 'message': 'Valid 10-digit phone number'}
    else:
        results['phone'] = {'ok': False, 'message': 'Enter a valid 10-digit phone number'}

    email = (email or '').strip()
    if email and EMAIL_RE.match(email):
        results['email'] = {'ok': True, 'message': 'Valid email format'}
    else:
        results['email'] = {'ok': False, 'message': 'Enter a valid email address'}

    company_name = (company_name or '').strip()
    if company_name:
        results['companyName'] = {'ok': True, 'message': 'Looks good'}
    else:
        results['companyName'] = {'ok': False, 'message': 'Company name is required'}

    return results


def all_valid(results):
    return all(r['ok'] for r in results.values())
