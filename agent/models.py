from django.db import models


class AgentSettings(models.Model):
    AUTO_REPLY_CHOICES = (
        ('full_auto', 'رد تلقائي كامل'),
        ('suggest_only', 'اقتراح فقط'),
        ('off', 'إيقاف تام'),
    )

    is_globally_active = models.BooleanField(default=True)
    auto_reply_mode = models.CharField(max_length=15, choices=AUTO_REPLY_CHOICES, default='full_auto')
    
    # Analytics & Meta Integration Fields
    fb_page_url = models.URLField(max_length=500, default="https://www.facebook.com/profile.php?id=61591261844925")
    fb_page_id = models.CharField(max_length=100, default="61591261844925")
    fb_followers_override = models.IntegerField(default=1250)
    fb_reach_override = models.IntegerField(default=4800)
    ig_page_url = models.URLField(max_length=500, default="https://instagram.com/dummy")
    ig_followers_override = models.IntegerField(default=0)
    is_meta_connected = models.BooleanField(default=True)
    is_google_connected = models.BooleanField(default=False)
    meta_access_token = models.TextField(blank=True, default='')
    last_meta_sync = models.DateTimeField(null=True, blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1  # Singleton - صف واحد بس دايمًا
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "إعدادات الإيجنت"


class AgentActionRequest(models.Model):
    ACTION_TYPE_CHOICES = (
        ('add_product', 'إضافة منتج جديد'),
        ('update_product_price', 'تعديل سعر منتج'),
        ('mark_unavailable', 'تعطيل توفر منتج'),
        ('other', 'أخرى'),
    )
    STATUS_CHOICES = (
        ('pending', 'قيد الانتظار'),
        ('approved', 'تمت الموافقة'),
        ('rejected', 'مرفوض'),
    )

    action_type = models.CharField(max_length=30, choices=ACTION_TYPE_CHOICES)
    payload = models.JSONField()  # كل البيانات المستخرجة (المنتج، السعر، الشحن...)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_action_type_display()} - {self.status}"


class MetaPostCache(models.Model):
    post_id = models.CharField(max_length=100, unique=True)
    platform = models.CharField(max_length=20, choices=[('facebook', 'Facebook'), ('instagram', 'Instagram')])
    caption = models.TextField(blank=True, default='')
    image_url = models.URLField(max_length=500, blank=True, default='')
    likes = models.IntegerField(default=0)
    comments = models.IntegerField(default=0)
    shares = models.IntegerField(default=0)
    engagement_rate = models.FloatField(default=0.0)
    posted_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-posted_at']

    def __str__(self):
        return f'{self.platform}: {self.post_id}'

class WebPageVisit(models.Model):
    path = models.CharField(max_length=500)
    session_key = models.CharField(max_length=100, blank=True, default='')
    referrer_type = models.CharField(
        max_length=20,
        choices=[('direct', 'Direct'), ('social', 'Social'), ('organic', 'Organic'), ('referral', 'Referral')],
        default='direct'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['path', 'created_at']),
            models.Index(fields=['referrer_type']),
        ]

    def __str__(self):
        return f'{self.path} @ {self.created_at}'