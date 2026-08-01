from django.contrib.auth.models import User
from django.db import models


class LoginEvent(models.Model):
    """Append-only audit record for every sign-in attempt -- matches the
    mockup's Step 1 copy ('every sign-in audited'). Kept independent of
    Django's own request logs so an examiner can reconstruct who
    signed in (or tried to), when, and from where."""
    email_attempted = models.EmailField()
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='login_events')
    success = models.BooleanField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'login_events'
        ordering = ['-created_at']

    def __str__(self):
        outcome = 'success' if self.success else 'failed'
        return f'{self.email_attempted} — {outcome} @ {self.created_at:%Y-%m-%d %H:%M}'
