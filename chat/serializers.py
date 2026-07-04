from rest_framework import serializers
from .models import ChatConversation, ChatMessage

class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'sender_type', 'content', 'timestamp']

class ChatConversationSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ChatConversation
        fields = ['id', 'customer_identifier', 'customer_name', 'status', 'is_agent_active', 'force_agent_auto', 'created_at', 'last_message_at', 'messages']
