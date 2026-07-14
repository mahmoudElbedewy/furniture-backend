import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatConversation, ChatMessage
from agent.models import AgentSettings
from agent.customer_agent import get_agent_reply
from accounts.identity import verify_identity_token



class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.room_group_name = f"chat_{self.conversation_id}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name, self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message")
        sender_type = text_data_json.get("sender_type", "customer")
        context_data = text_data_json.get("context")
        identity_token = text_data_json.get("identity_token")

        if not message:
            return
        
        if sender_type == "customer":
            authorized = await self.is_authorized_customer(identity_token)
            if not authorized:
                return 

        saved_msg = await self.save_message(
            self.conversation_id, sender_type, message
        )

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": saved_msg["content"],
                "sender_type": saved_msg["sender_type"],
                "timestamp": saved_msg["timestamp"],
            },
        )

        if sender_type == "customer":
            asyncio.create_task(
                self.process_agent_reply(message, context_data)
            )

    @database_sync_to_async
    def is_authorized_customer(self, identity_token):
        try:
            conversation = ChatConversation.objects.get(id=self.conversation_id)
        except ChatConversation.DoesNotExist:
            return False

        user = self.scope.get("user")
        if user and getattr(user, "is_authenticated", False):
            email = (user.email or "").strip().lower()
            identifier = email.split("@")[0] if email and "@" in email else str(user.id)
            return conversation.customer_identifier == identifier

        identifier = verify_identity_token(identity_token)
        return bool(identifier) and conversation.customer_identifier == identifier

    async def process_agent_reply(self, customer_message, context_data=None):
        agent_status = await self.get_agent_status()
        if not agent_status["is_active"] or agent_status["mode"] == "off":
            return

        history = await self.get_conversation_history()

        reply_content = await get_agent_reply(
            agent_status["conversation"],
            history,
            customer_message,
            context_data,
        )

        if agent_status["mode"] == "full_auto":
            saved_reply = await self.save_message(
                self.conversation_id, "agent", reply_content
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": saved_reply["content"],
                    "sender_type": saved_reply["sender_type"],
                    "timestamp": saved_reply["timestamp"],
                },
            )

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "message": event["message"],
                    "sender_type": event["sender_type"],
                    "timestamp": event["timestamp"],
                }
            )
        )

    @database_sync_to_async
    def save_message(self, conversation_id, sender_type, content):
        conversation = ChatConversation.objects.get(id=conversation_id)
        msg = ChatMessage.objects.create(
            conversation=conversation,
            sender_type=sender_type,
            content=content,
        )
        if sender_type == "customer" and conversation.status != "needs_admin":
            conversation.status = "open"
            conversation.save()

        if sender_type == "customer":
            from .notifications import send_ntfy_alert

            send_ntfy_alert(
                title="💬 رسالة عميل جديدة",
                message=f"{conversation.customer_name}: {content}",
            )

        return {
            "content": msg.content,
            "sender_type": msg.sender_type,
            "timestamp": msg.timestamp.isoformat(),
        }

    @database_sync_to_async
    def get_agent_status(self):
        conversation = ChatConversation.objects.get(id=self.conversation_id)
        settings = AgentSettings.load()
        return {
            "conversation": conversation,
            "is_active": conversation.is_agent_active and settings.is_globally_active,
            "mode": settings.auto_reply_mode,
            "needs_admin": conversation.status == "needs_admin",
        }

    @database_sync_to_async
    def get_conversation_history(self):
        conversation = ChatConversation.objects.get(id=self.conversation_id)
        messages = conversation.messages.all().order_by("timestamp")
        return [{"role": msg.sender_type, "content": msg.content} for msg in messages]
