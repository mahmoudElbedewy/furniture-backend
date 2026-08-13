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
    customer_last_read_at = models.DateTimeField(blank=True, null=True)
    admin_last_read_at = models.DateTimeField(blank=True, null=True)
    last_page_context = models.JSONField(default=dict, blank=True)
    page_history = models.JSONField(default=list, blank=True)
    context_updated_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer_identifier"], name="unique_chat_per_customer"
            )
        ]

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
    content = models.TextField(blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.sender_type}] {self.content[:40]}"


class ChatAttachment(models.Model):
    message = models.ForeignKey(
        ChatMessage, on_delete=models.CASCADE, related_name="attachments"
    )
    image = models.ImageField(upload_to="chat_attachments/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.image.name


class CustomerPushSubscription(models.Model):
    customer_identifier = models.CharField(max_length=100, db_index=True)
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    user_agent = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.customer_identifier} - {self.endpoint[:50]}"
