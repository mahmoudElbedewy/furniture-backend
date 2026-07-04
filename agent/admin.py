from django.contrib import admin
from django.utils import timezone
from django.contrib import messages
from .models import AgentSettings, AgentActionRequest


@admin.register(AgentSettings)
class AgentSettingsAdmin(admin.ModelAdmin):
    list_display = ('auto_reply_mode', 'is_globally_active', 'updated_at')

    def has_add_permission(self, request):
        # Singleton - مفيش إضافة صفوف جديدة
        return not AgentSettings.objects.exists()


@admin.register(AgentActionRequest)
class AgentActionRequestAdmin(admin.ModelAdmin):
    list_display = ('action_type', 'status', 'requested_at', 'reviewed_at')
    list_filter = ('status', 'action_type')
    readonly_fields = ('action_type', 'payload', 'reason', 'requested_at')
    actions = ('approve_requests', 'reject_requests')

    def approve_requests(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='approved', reviewed_at=timezone.now()
        )
        self.message_user(request, f"تمت الموافقة على {updated} طلب.", messages.SUCCESS)
    approve_requests.short_description = "✅ الموافقة على الطلبات المختارة"

    def reject_requests(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='rejected', reviewed_at=timezone.now()
        )
        self.message_user(request, f"تم رفض {updated} طلب.", messages.WARNING)
    reject_requests.short_description = "❌ رفض الطلبات المختارة"