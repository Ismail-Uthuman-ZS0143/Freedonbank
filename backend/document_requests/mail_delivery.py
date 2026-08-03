"""Real outbound email delivery. Primary/default design is direct-to-MX --
no SMTP relay/provider account, mirroring the pattern already used in the
sibling StackPulse project (see stackpulse/src/main/java/com/falcon/service/
{EmailService,DirectMailSender,MxResolver,DomainWhitelistService}.java): for
each recipient, resolve their domain's real MX record via DNS, then connect
directly to that mail server and hand off the message with opportunistic
STARTTLS. No credentials anywhere for this path.

An optional authenticated-relay override exists on top of that (MAIL_RELAY_*
settings) for environments where port 25 has no outbound route at all --
confirmed to be the case for this dev sandbox's network via a direct raw
socket test (Network unreachable), while submission ports (587) are open.
When configured, it takes over delivery entirely for that environment; the
credential-free direct-to-MX path remains the default and requires no
config to work once deployed somewhere port 25 is actually reachable.

Delivery is fail-safe: any failure is logged and swallowed, never raised
back to the caller -- Steps 3/4/5/6's flows must not break just because an
email couldn't be delivered. The RequestEmail audit row is always created
regardless of delivery outcome (see email_service.py); this module only
answers "did the hand-off succeed."
"""
import ipaddress
import logging
import smtplib
import socket
from email.mime.text import MIMEText
from email.utils import formataddr

import dns.exception
import dns.resolver
from django.conf import settings

logger = logging.getLogger(__name__)

_mx_cache = {}


def _resolve_ip(host):
    """Resolves `host` to an IP literal via dns.resolver instead of letting
    smtplib fall through to the system resolver's getaddrinfo(). Found by
    reproducing a real worker crash: smtplib.SMTP(host, port, timeout=N)'s
    `timeout` only ever governs the connect() call, never DNS resolution --
    and in this sandbox, getaddrinfo() hangs indefinitely on real hostnames
    (confirmed: a direct connect to a resolved real MX host blocked for
    40+ seconds despite timeout=10, eventually exceeding gunicorn's worker
    timeout and getting the worker SIGABRT-killed mid-request). dns.resolver
    has its own bounded, working timeout path here, so resolve through it
    and hand smtplib a bare IP -- never a hostname."""
    try:
        ipaddress.ip_address(host)
        return host  # already a literal, e.g. from MAIL_TEST_SERVER=127.0.0.1:...
    except ValueError:
        pass
    answers = dns.resolver.resolve(host, 'A', lifetime=settings.MAIL_DNS_TIMEOUT_SECONDS)
    return str(answers[0])


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


def _relay_configured():
    return bool(settings.MAIL_RELAY_HOST and settings.MAIL_RELAY_USERNAME and settings.MAIL_RELAY_PASSWORD)


def send_direct_email(to_email, subject, body_text):
    """Attempts real delivery of one already-composed plain-text email.
    Returns (attempted, delivered): `attempted` is True only once a real
    SMTP conversation was actually opened (False when skipped outright --
    disabled, or domain not allowed); `delivered` is True only on a
    successful hand-off. Never raises.

    Three delivery modes, in this precedence order:
    1. MAIL_TEST_SERVER set -- routes to a local/known test address.
    2. MAIL_RELAY_* all set -- authenticated SMTP submission (port 587)
       through a real mailbox. Exists because this dev sandbox's network
       has no route out on port 25 at all (confirmed via a direct raw
       socket test), while submission ports are open -- so a real
       mailbox's app password is the only way to get real delivery from
       here. The relay provider will reject (or silently rewrite) a From
       address it doesn't own, so envelope-from and the From header are
       both the authenticated relay account, not MAIL_FROM_ADDRESS.
    3. Otherwise -- real direct-to-MX (the default/primary design, no
       credentials, matches the sibling StackPulse project)."""
    if not settings.MAIL_ENABLED:
        logger.debug('Direct mail delivery disabled (MAIL_ENABLED=false) -- not attempting: %r', subject)
        return False, False
    if not _is_domain_allowed(to_email):
        logger.warning('Email blocked -- domain not in MAIL_ALLOWED_DOMAINS: %s', to_email)
        return False, False

    domain = to_email.rsplit('@', 1)[-1]
    use_test_server = bool(settings.MAIL_TEST_SERVER)
    use_relay = not use_test_server and _relay_configured()

    if use_test_server:
        host, _, port_str = settings.MAIL_TEST_SERVER.partition(':')
        port = int(port_str or 25)
        logger.info('MAIL_TEST_SERVER set -- routing to %s instead of real MX for %s', settings.MAIL_TEST_SERVER, domain)
    elif use_relay:
        host = settings.MAIL_RELAY_HOST
        port = settings.MAIL_RELAY_PORT
        logger.info('MAIL_RELAY_HOST set -- routing via authenticated relay %s:%s for %s', host, port, domain)
    else:
        host = _resolve_mx(domain)
        port = settings.MAIL_SMTP_PORT

    from_address = settings.MAIL_RELAY_USERNAME if use_relay else settings.MAIL_FROM_ADDRESS
    message = MIMEText(body_text, 'plain', 'utf-8')
    message['Subject'] = subject
    message['From'] = formataddr((settings.MAIL_FROM_NAME, from_address))
    message['To'] = to_email

    try:
        # A real hostname can genuinely fail to resolve (NXDOMAIN/timeout),
        # so _resolve_ip() must stay inside this try -- but MAIL_TEST_SERVER's
        # and the relay's hosts are known/trusted addresses, passed through
        # untouched (no real DNS query needed for either).
        ip = host if (use_test_server or use_relay) else _resolve_ip(host)
        with smtplib.SMTP(ip, port, timeout=settings.MAIL_TIMEOUT_SECONDS) as smtp:
            smtp.ehlo()
            if smtp.has_extn('STARTTLS'):
                smtp.starttls()
                smtp.ehlo()
            if use_relay:
                smtp.login(settings.MAIL_RELAY_USERNAME, settings.MAIL_RELAY_PASSWORD)
            smtp.sendmail(from_address, [to_email], message.as_string())
        logger.info('Email delivered via %s (%s):%s to %s -- subject: %r', host, ip, port, to_email, subject)
        return True, True
    except (smtplib.SMTPException, socket.error, OSError, dns.exception.DNSException) as exc:
        logger.error('Failed to deliver email to %s (mx=%s:%s) -- %s', to_email, host, port, exc)
        return True, False


def clear_mx_cache():
    """Useful for tests or after a config/DNS change."""
    _mx_cache.clear()
