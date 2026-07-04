from django.db import models


class AdminNotification(models.Model):
    TYPE_CHOICES = (
        ('new_order', 'أوردر جديد'),
        ('new_chat_message', 'رسالة شات جديدة'),
        ('agent_action_request', 'طلب موافقة من الإيجنت'),
    )

    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    related_object_id = models.CharField(max_length=100)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    sent_via_telegram = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_type_display()} - {self.message[:40]}"