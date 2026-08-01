"""Real outbound email delivery -- direct-to-MX, no SMTP relay/provider
account, mirroring the pattern already used in the sibling StackPulse
project (see stackpulse/src/main/java/com/falcon/service/{EmailService,
DirectMailSender,MxResolver,DomainWhitelistService}.java).

For each recipient, resolve their domain's real MX record via DNS, then
connect directly to that mail server and hand off the message with
opportunistic STARTTLS. No third-party account or API key exists anywhere
in this codebase -- this trades away provider conveniences (SPF/DKIM
alignment, bounce webhooks, sending-reputation management) for zero
external dependency, the same tradeoff StackPulse made.

Delivery is fail-safe: any failure is logged and swallowed, never raised
back to the caller -- Steps 3/4/5/6's flows must not break just because an
email couldn't be delivered. The RequestEmail audit row is always created
regardless of delivery outcome (see email_service.py); this module only
answers "did the hand-off to the recipient's mail server succeed."
"""
import logging
import smtplib
import socket
from email.mime.text import MIMEText
from email.utils import formataddr

import dns.resolver
from django.conf import settings

logger = logging.getLogger(__name__)

_mx_cache = {}


def _resolve_mx(domain):
    """Real DNS MX lookup, sorted by preference (lowest number wins), with
    an in-memory cache and a fallback to the domain itself if no MX record
    exists (RFC 5321) or the lookup fails outright."""
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=settings.MAIL_DNS_TIMEOUT_SECONDS)
        best = min(answers, key=lambda r: r.preference)
        host = str(best.exchange).rstrip('.')
    except Exception as exc:
        logger.warning('MX lookup failed for %s (%s) -- falling back to domain itself', domain, exc)
        host = domain
    _mx_cache[domain] = host
    return host


def _is_domain_allowed(email_address):
    if '@' not in email_address:
        return False
    domain = email_address.rsplit('@', 1)[-1].lower()
    return domain in settings.MAIL_ALLOWED_DOMAINS


def send_direct_email(to_email, subject, body_text):
    """Attempts real delivery of one already-composed plain-text email.
    Returns (attempted, delivered): `attempted` is True only once a real
    SMTP conversation was actually opened (False when skipped outright --
    disabled, or domain not allowed); `delivered` is True only on a
    successful hand-off. Never raises."""
    if not settings.MAIL_ENABLED:
        logger.debug('Direct mail delivery disabled (MAIL_ENABLED=false) -- not attempting: %r', subject)
        return False, False
    if not _is_domain_allowed(to_email):
        logger.warning('Email blocked -- domain not in MAIL_ALLOWED_DOMAINS: %s', to_email)
        return False, False

    domain = to_email.rsplit('@', 1)[-1]
    if settings.MAIL_TEST_SERVER:
        host, _, port_str = settings.MAIL_TEST_SERVER.partition(':')
        port = int(port_str or 25)
        logger.info('MAIL_TEST_SERVER set -- routing to %s instead of real MX for %s', settings.MAIL_TEST_SERVER, domain)
    else:
        host = _resolve_mx(domain)
        port = settings.MAIL_SMTP_PORT

    message = MIMEText(body_text, 'plain', 'utf-8')
    message['Subject'] = subject
    message['From'] = formataddr((settings.MAIL_FROM_NAME, settings.MAIL_FROM_ADDRESS))
    message['To'] = to_email

    try:
        with smtplib.SMTP(host, port, timeout=settings.MAIL_TIMEOUT_SECONDS) as smtp:
            smtp.ehlo()
            if smtp.has_extn('STARTTLS'):
                smtp.starttls()
                smtp.ehlo()
            smtp.sendmail(settings.MAIL_FROM_ADDRESS, [to_email], message.as_string())
        logger.info('Email delivered via %s:%s to %s -- subject: %r', host, port, to_email, subject)
        return True, True
    except (smtplib.SMTPException, socket.error, OSError) as exc:
        logger.error('Failed to deliver email to %s (mx=%s:%s) -- %s', to_email, host, port, exc)
        return True, False


def clear_mx_cache():
    """Useful for tests or after a config/DNS change."""
    _mx_cache.clear()
