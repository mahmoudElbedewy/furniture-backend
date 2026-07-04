import uuid
from django.db import models


class Supplier(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('suspended', 'Suspended'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel_name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=150, blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.channel_name