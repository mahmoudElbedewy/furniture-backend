from django.contrib import admin
from .models import AdminNotification


@admin.register(AdminNotification)
class AdminNotificationAdmin(admin.ModelAdmin):
    list_display = ('type', 'is_read', 'sent_via_telegram', 'created_at')
    list_filter = ('type', 'is_read', 'sent_via_telegram')
    search_fields = ('message', 'related_object_id')