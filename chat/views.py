from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone
from .models import (
    ChatAttachment,
    ChatConversation,
    ChatMessage,
    CustomerPushSubscription,
)
from .serializers import (
    ChatConversationSerializer,
    ChatMessageSerializer,
    CustomerPushSubscriptionSerializer,
)
from agent.models import AgentSettings
from agent.customer_agent import get_agent_reply
from asgiref.sync import async_to_sync
import uuid
from django.http import JsonResponse
import json

from django.conf import settings
import requests
from accounts.identity import issue_identity_token, verify_identity_token, resolve_identifier_for_request


def with_unread_counts(queryset):
    return queryset.annotate(
        customer_unread_count=Count(
            "messages",
            filter=(
                Q(messages__sender_type__in=["admin", "agent"])
                & (
                    Q(customer_last_read_at__isnull=True)
                    | Q(messages__timestamp__gt=models.F("customer_last_read_at"))
                )
            ),
        ),
        admin_unread_count=Count(
            "messages",
            filter=(
                Q(messages__sender_type="customer")
                & (
                    Q(admin_last_read_at__isnull=True)
                    | Q(messages__timestamp__gt=models.F("admin_last_read_at"))
                )
            ),
        ),
    )


def attach_unread_counts(conversation):
    customer_filter = Q(sender_type__in=["admin", "agent"])
    admin_filter = Q(sender_type="customer")
    if conversation.customer_last_read_at:
        customer_filter &= Q(timestamp__gt=conversation.customer_last_read_at)
    if conversation.admin_last_read_at:
        admin_filter &= Q(timestamp__gt=conversation.admin_last_read_at)
    conversation.customer_unread_count = conversation.messages.filter(customer_filter).count()
    conversation.admin_unread_count = conversation.messages.filter(admin_filter).count()
    return conversation


def add_attachments(message, files):
    for image_file in files:
        ChatAttachment.objects.create(message=message, image=image_file)

def resolve_customer_identifier(request, data=None):
    """إصلاح A1: الزائر بقى مايقدرش يقرا شات حد تاني بمجرد إنه يبعت
    customer_identifier بتاعه. المعرّف بقى إما من الـ JWT (مسجّلين) أو من
    identity_token موقّع من السيرفر (زوار) بس."""
    return resolve_identifier_for_request(request, data)


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
        if request.user.is_authenticated:
            identifier = resolve_customer_identifier(request)
            identity_token = None
        else:
            token = request.data.get("identity_token")
            identifier = verify_identity_token(token) if token else None
            if not identifier:
                identifier = f"guest_{uuid.uuid4().hex[:12]}"
            identity_token = issue_identity_token(identifier)

        customer_name = resolve_customer_name(request)
        conversation, created = ChatConversation.objects.get_or_create(
            customer_identifier=identifier,
            defaults={"customer_name": customer_name},
        )
        if not created and customer_name and conversation.customer_name != customer_name:
            conversation.customer_name = customer_name
            conversation.save(update_fields=["customer_name", "last_message_at"])

        data = ChatConversationSerializer(
            attach_unread_counts(conversation), context={"request": request}
        ).data
        data["customer_identifier"] = identifier
        if identity_token:
            data["identity_token"] = identity_token
        return Response(data, status=status.HTTP_200_OK)


class ChatHistoryView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, conversation_id):
        conversation = get_object_or_404(ChatConversation, id=conversation_id)

        user_identifier = resolve_customer_identifier(request, request.GET)

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

        mark_read = request.query_params.get("mark_read", "true").lower()
        if mark_read in ("1", "true", "yes"):
            conversation.customer_last_read_at = timezone.now()
            conversation.save(update_fields=["customer_last_read_at", "last_message_at"])

        messages = conversation.messages.all().order_by("timestamp")
        serializer = ChatMessageSerializer(
            messages, many=True, context={"request": request}
        )
        return Response(
            {
                "conversation_status": conversation.status,
                "customer_unread_count": attach_unread_counts(conversation).customer_unread_count,
                "messages": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class ChatSendMessageView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

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

        content = (request.data.get("message") or request.data.get("content") or "").strip()
        sender_type = request.data.get("sender_type", "customer")
        context_data = request.data.get("context")
        if isinstance(context_data, str):
            try:
                context_data = json.loads(context_data)
            except json.JSONDecodeError:
                context_data = None
        images = request.FILES.getlist("images")

        if not content and not images:
            return Response(
                {"error": "message or images are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer_message = ChatMessage.objects.create(
            conversation=conversation, sender_type=sender_type, content=content
        )
        add_attachments(customer_message, images)

        created_messages = [customer_message]

        if sender_type == "customer":
            from .notifications import send_ntfy_alert

            send_ntfy_alert(
                title="💬 رسالة عميل جديدة",
                message=f"{conversation.customer_name}: {content or 'صورة جديدة'}",
            )

        created_messages = [customer_message]

        if sender_type == "customer" and conversation.status != "needs_admin":
            conversation.status = "open"
            conversation.save(update_fields=["status", "last_message_at"])

        if sender_type == "customer" and content:
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
                                created_messages,
                                many=True,
                                context={"request": request},
                            ).data,
                            "agent_error": str(exc),
                        },
                        status=status.HTTP_202_ACCEPTED,
                    )

        return Response(
            {
                "messages": ChatMessageSerializer(
                    created_messages, many=True, context={"request": request}
                ).data
            },
            status=status.HTTP_201_CREATED,
        )


class CustomerUnreadView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        identifier = resolve_customer_identifier(request, request.GET)
        if not identifier:
            return Response(
                {"error": "customer_identifier is required"},
                status=status.HTTP_403_FORBIDDEN,
            )
        conversation = ChatConversation.objects.filter(
            customer_identifier=identifier
        ).first()
        if not conversation:
            return Response({"conversation_id": None, "unread_count": 0})

        attach_unread_counts(conversation)
        return Response(
            {
                "conversation_id": conversation.id,
                "unread_count": conversation.customer_unread_count,
            }
        )


class CustomerPushSubscriptionView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        identifier = resolve_customer_identifier(request)
        if not identifier:
            return Response(
                {"error": "customer_identifier is required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CustomerPushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscription, _ = CustomerPushSubscription.objects.update_or_create(
            endpoint=serializer.validated_data["endpoint"],
            defaults={
                "customer_identifier": identifier,
                "p256dh": serializer.validated_data["p256dh"],
                "auth": serializer.validated_data["auth"],
                "user_agent": serializer.validated_data.get("user_agent", ""),
                "is_active": True,
            },
        )
        return Response(
            CustomerPushSubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED,
        )


class WebPushConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(
            {"vapid_public_key": getattr(settings, "WEB_PUSH_VAPID_PUBLIC_KEY", "")}
        )


def ntfy_test_view(request):
    try:
        r = requests.post(
            "https://ntfy.sh/furniture_alert_messages",
            data="اختبار من HF".encode("utf-8"),
            headers={"Title": "اختبار الإشعارات".encode("utf-8")},
            timeout=10,
        )
        return JsonResponse({"ok": True, "status": r.status_code, "response": r.text})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})


def ntfy_test_view(request):
    try:
        from .notifications import send_ntfy_alert

        send_ntfy_alert(title="اختبار الإشعارات", message="اختبار من HF")
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})
