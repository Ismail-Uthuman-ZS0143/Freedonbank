"""Disk-backed storage for Step 4 customer uploads. Same pattern as
appstore's credit_file_server usecase: files live on disk under
settings.UPLOAD_STORAGE_ROOT, organized by request and checklist item, with
only the relative path stored in the DB.
"""
import os
import re

from django.conf import settings

_UNSAFE_CHARS_RE = re.compile(r'[^\w\s.\-()]')
_WHITESPACE_RE = re.compile(r'\s+')


def _sanitize(name: str, max_len: int = 120) -> str:
    name = _UNSAFE_CHARS_RE.sub('', name or '').strip()
    name = _WHITESPACE_RE.sub(' ', name)
    return name[:max_len] or 'untitled'


def build_relative_path(doc_request, checklist_item_name, upload_id, file_name) -> str:
    """{Company or borrower name} (req{id}) -> {checklist item} -> file."""
    request_folder = f"{_sanitize(doc_request.company_name or doc_request.borrower_name)} (req{doc_request.id})"
    item_folder = _sanitize(checklist_item_name) if checklist_item_name else '_unfiled'
    safe_file_name = f"{upload_id}_{_sanitize(file_name)}"
    return os.path.join(request_folder, item_folder, safe_file_name)


def absolute_path(relative_path: str) -> str:
    return os.path.join(settings.UPLOAD_STORAGE_ROOT, relative_path)


def write_file(relative_path: str, data: bytes) -> None:
    abs_path = absolute_path(relative_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'wb') as f:
        f.write(data)


def read_file(relative_path: str) -> bytes:
    with open(absolute_path(relative_path), 'rb') as f:
        return f.read()
