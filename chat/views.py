from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from .models import ChatConversation, ChatMessage
from .serializers import ChatConversationSerializer, ChatMessageSerializer
from agent.models import AgentSettings
from agent.customer_agent import get_agent_reply
from asgiref.sync import async_to_sync
import uuid


def resolve_customer_identifier(request, data=None):
    """معرّف المحادثة: جزء الإيميل قبل @ للمسجّلين، أو session_id للزوار."""
    if request.user.is_authenticated:
        email = (request.user.email or "").strip().lower()
        if email and "@" in email:
            return email.split("@")[0]
        return str(request.user.id)

    payload = data if data is not None else getattr(request, "data", {})
    identifier = payload.get("customer_identifier") or payload.get("session_id")
    if identifier:
        return str(identifier).strip()
    return None


def resolve_customer_name(request, data=None):
    payload = data if data is not None else getattr(request, "data", {})
    if request.user.is_authenticated:
        return (
            request.user.full_name
            or request.user.email.split("@")[0]
            or "عميل"
        )
    return payload.get("customer_name") or "زائر"


class ChatStartView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        identifier = resolve_customer_identifier(request)
        created_session = False
        if not identifier:
            identifier = f"guest_{uuid.uuid4().hex[:12]}"
            created_session = True

        customer_name = resolve_customer_name(request)
        force_new = request.data.get("force_new", False)

        conversation = None
        if not force_new:
            conversation = (
                ChatConversation.objects.filter(
                    customer_identifier=identifier,
                    status="open",
                )
                .order_by("-last_message_at")
                .first()
            )

        if not conversation:
            conversation = ChatConversation.objects.create(
                customer_identifier=identifier,
                customer_name=customer_name,
            )

        data = ChatConversationSerializer(conversation).data
        data["customer_identifier"] = identifier
        if created_session or not request.user.is_authenticated:
            data["session_id"] = identifier
        return Response(data, status=status.HTTP_200_OK)


class ChatHistoryView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, conversation_id):
        conversation = get_object_or_404(ChatConversation, id=conversation_id)

        user_identifier = resolve_customer_identifier(
            request, request.GET
        ) or request.GET.get("customer_identifier") or request.GET.get("session_id")

        if not user_identifier:
            return Response(
                {"error": "customer_identifier is required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if conversation.customer_identifier != user_identifier:
            return Response(
                {"error": "Unauthorized access to conversation"},
                status=status.HTTP_403_FORBIDDEN,
            )

        messages = conversation.messages.all().order_by("timestamp")
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(
            {"conversation_status": conversation.status, "messages": serializer.data},
            status=status.HTTP_200_OK,
        )


class ChatSendMessageView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, conversation_id):
        conversation = get_object_or_404(ChatConversation, id=conversation_id)

        user_identifier = resolve_customer_identifier(request)
        if not user_identifier:
            return Response(
                {"error": "customer_identifier is required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if conversation.customer_identifier != user_identifier:
            return Response(
                {"error": "Unauthorized access to conversation"},
                status=status.HTTP_403_FORBIDDEN,
            )

        content = request.data.get("message") or request.data.get("content")
        sender_type = request.data.get("sender_type", "customer")
        context_data = request.data.get("context")

        if not content:
            return Response(
                {"error": "message is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        customer_message = ChatMessage.objects.create(
            conversation=conversation, sender_type=sender_type, content=content
        )

        created_messages = [customer_message]

        if sender_type == "customer" and conversation.status != "needs_admin":
            conversation.status = "open"
            conversation.save(update_fields=["status", "last_message_at"])

        if sender_type == "customer":
            settings = AgentSettings.load()
            if (
                conversation.is_agent_active
                and settings.is_globally_active
                and settings.auto_reply_mode == "full_auto"
            ):
                history = [
                    {"role": msg.sender_type, "content": msg.content}
                    for msg in conversation.messages.all().order_by("timestamp")
                ]

                try:
                    reply_content = async_to_sync(get_agent_reply)(
                        conversation, history, content, context_data
                    )
                    agent_message = ChatMessage.objects.create(
                        conversation=conversation,
                        sender_type="agent",
                        content=reply_content,
                    )
                    created_messages.append(agent_message)
                except Exception as exc:
                    return Response(
                        {
                            "messages": ChatMessageSerializer(
                                created_messages, many=True
                            ).data,
                            "agent_error": str(exc),
                        },
                        status=status.HTTP_202_ACCEPTED,
                    )

        return Response(
            {"messages": ChatMessageSerializer(created_messages, many=True).data},
            status=status.HTTP_201_CREATED,
        )
