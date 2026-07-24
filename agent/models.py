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
    fb_page_url = models.URLField(max_length=500, blank=True, default="")
    fb_page_id = models.CharField(max_length=100, blank=True, default="")
    fb_followers_override = models.IntegerField(null=True, blank=True, default=None)
    fb_reach_override = models.IntegerField(null=True, blank=True, default=None)
    ig_page_url = models.URLField(max_length=500, blank=True, default="")
    ig_followers_override = models.IntegerField(null=True, blank=True, default=None)
    is_meta_connected = models.BooleanField(default=False)
    is_google_connected = models.BooleanField(default=False)
    meta_access_token = models.TextField(blank=True, default='')
    last_meta_sync = models.DateTimeField(null=True, blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    ga4_property_id = models.CharField(max_length=50, blank=True, default='')
    ga4_service_account_json = models.TextField(blank=True, default='')
    is_ga4_connected = models.BooleanField(default=False)
    last_ga4_sync = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        self.pk = 1  
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
    
class FacebookPostMetric(models.Model):
    """Replaces MetaPostCache — richer, keeps UTM campaign for join with GA4."""
    post_id = models.CharField(max_length=100, unique=True)
    message = models.TextField(blank=True, default='')
    image_url = models.URLField(max_length=500, blank=True, default='')
    permalink_url = models.URLField(max_length=500, blank=True, default='')
    utm_campaign = models.CharField(max_length=150, blank=True, default='', db_index=True)

    reach = models.IntegerField(default=0)
    impressions = models.IntegerField(default=0)
    likes = models.IntegerField(default=0)
    comments = models.IntegerField(default=0)
    shares = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    video_views = models.IntegerField(default=0)
    post_type = models.CharField(max_length=20, default='status')  # photo/video/link/status

    engagement_rate = models.FloatField(default=0.0)
    published_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published_at']
        indexes = [models.Index(fields=['published_at'])]


class DailyMetricSnapshot(models.Model):
    """Flexible daily aggregate row — one per (date, source, metric)."""
    SOURCE_CHOICES = (
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('ga4', 'Google Analytics'),
        ('site', 'Internal WebPageVisit'),
    )
    date = models.DateField(db_index=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    metric_name = models.CharField(max_length=50)  # e.g. 'followers','reach','sessions','conversions'
    value = models.FloatField(default=0)

    class Meta:
        unique_together = ('date', 'source', 'metric_name')
        indexes = [models.Index(fields=['source', 'metric_name', 'date'])]


class GACampaignSession(models.Model):
    """GA4 sessions/conversions attributed to a utm_campaign (usually = post_<post_id>)."""
    date = models.DateField(db_index=True)
    utm_campaign = models.CharField(max_length=150, db_index=True)
    sessions = models.IntegerField(default=0)
    conversions = models.IntegerField(default=0)
    engaged_sessions = models.IntegerField(default=0)

    class Meta:
        unique_together = ('date', 'utm_campaign')


class GADailyTraffic(models.Model):
    """Whole-site GA4 daily rollup for the Web Traffic tab."""
    date = models.DateField(unique=True)
    sessions = models.IntegerField(default=0)
    users = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0)
    bounce_rate = models.FloatField(default=0.0)
    avg_session_duration_seconds = models.FloatField(default=0.0)
    conversions = models.IntegerField(default=0)
    source_organic = models.IntegerField(default=0)
    source_social = models.IntegerField(default=0)
    source_direct = models.IntegerField(default=0)
    source_referral = models.IntegerField(default=0)


class GATopPage(models.Model):
    date = models.DateField(db_index=True)
    page_path = models.CharField(max_length=500)
    views = models.IntegerField(default=0)
    unique_visitors = models.IntegerField(default=0)
    bounce_rate = models.FloatField(default=0.0)
    avg_duration_seconds = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('date', 'page_path')
