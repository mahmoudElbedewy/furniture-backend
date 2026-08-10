from django.contrib import admin
from .models import ChatAttachment, ChatConversation, ChatMessage, CustomerPushSubscription


class ChatAttachmentInline(admin.TabularInline):
    model = ChatAttachment
    extra = 0
    readonly_fields = ('image', 'created_at')
    can_delete = False


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('sender_type', 'content', 'timestamp')
    can_delete = False


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'sender_type', 'timestamp')
    list_filter = ('sender_type',)
    search_fields = ('content', 'conversation__customer_identifier', 'conversation__customer_name')
    inlines = (ChatAttachmentInline,)


@admin.register(ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'customer_identifier', 'status', 'is_agent_active', 'last_message_at')
    list_filter = ('status', 'is_agent_active')
    search_fields = ('customer_name', 'customer_identifier')
    inlines = (ChatMessageInline,)


@admin.register(CustomerPushSubscription)
class CustomerPushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('customer_identifier', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('customer_identifier', 'endpoint')
