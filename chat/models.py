import uuid
from django.db import models


class ChatConversation(models.Model):
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('needs_admin', 'Needs Admin'),
        ('closed', 'Closed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_identifier = models.CharField(max_length=100)  # email prefix أو session_id
    customer_name = models.CharField(max_length=150, blank=True, null=True)
    is_agent_active = models.BooleanField(default=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    escalation_note = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.customer_name or self.customer_identifier} - {self.status}"


class ChatMessage(models.Model):
    SENDER_CHOICES = (
        ('customer', 'Customer'),
        ('agent', 'Agent'),
        ('admin', 'Admin'),
    )

    conversation = models.ForeignKey(ChatConversation, on_delete=models.CASCADE, related_name='messages')
    sender_type = models.CharField(max_length=10, choices=SENDER_CHOICES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.sender_type}] {self.content[:40]}"