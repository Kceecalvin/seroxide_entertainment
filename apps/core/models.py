from django.db import models


class ContactMessage(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} <{self.email}> — {self.subject or "(no subject)"}'


class EmailDelivery(models.Model):
    key = models.CharField(max_length=150, unique=True)
    kind = models.CharField(max_length=20, default='message')
    recipient = models.EmailField()
    subject = models.CharField(max_length=250)
    text = models.TextField(blank=True)
    html = models.TextField(blank=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, default='pending', db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
