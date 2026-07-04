from django.contrib import admin
from .models import ChatConversation, ChatMessage


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('sender_type', 'content', 'timestamp')
    can_delete = False


@admin.register(ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'customer_identifier', 'status', 'is_agent_active', 'last_message_at')
    list_filter = ('status', 'is_agent_active')
    search_fields = ('customer_name', 'customer_identifier')
    inlines = (ChatMessageInline,)