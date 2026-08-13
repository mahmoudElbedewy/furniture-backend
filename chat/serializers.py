from rest_framework import serializers
from .models import ChatAttachment, ChatConversation, ChatMessage, CustomerPushSubscription


class ChatAttachmentSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ChatAttachment
        fields = ["id", "image_url", "created_at"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        url = obj.image.url if obj.image else ""
        if request and url and not url.startswith("http"):
            return request.build_absolute_uri(url)
        return url


class ChatMessageSerializer(serializers.ModelSerializer):
    attachments = ChatAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ChatMessage
        fields = ['id', 'sender_type', 'content', 'timestamp', 'attachments']

class ChatConversationSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)
    customer_unread_count = serializers.IntegerField(read_only=True)
    admin_unread_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ChatConversation
        fields = [
            'id',
            'customer_identifier',
            'customer_name',
            'status',
            'is_agent_active',
            'customer_last_read_at',
            'admin_last_read_at',
            'last_page_context',
            'page_history',
            'context_updated_at',
            'created_at',
            'last_message_at',
            'customer_unread_count',
            'admin_unread_count',
            'messages',
        ]


class CustomerPushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerPushSubscription
        fields = ["id", "endpoint", "p256dh", "auth", "user_agent", "is_active"]
        read_only_fields = ["id", "is_active"]
