from rest_framework import viewsets, views
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import models
from django.db.models import Sum, Count, Q
from django.shortcuts import get_object_or_404
from django.core.files.storage import default_storage
from django.utils.text import slugify
from channels.layers import get_channel_layer
from accounts.permissions import IsAdminRole
from orders.models import Order, Commission, StorePayment
from catalog.models import Product
from chat.models import ChatAttachment, ChatConversation, ChatMessage
from agent.models import AgentSettings, AgentActionRequest
from agent.admin_agent import get_admin_reply
from agent.extractor import REQUIRED_FIELDS, extract_product_data
from telegram_bot.models import AdminNotification
from suppliers.models import Supplier
from chat.serializers import ChatConversationSerializer, ChatMessageSerializer
from suppliers.serializers import SupplierSerializer
from rest_framework import serializers
from rest_framework.decorators import action
from django.utils import timezone
from asgiref.sync import async_to_sync
import json
import uuid


def with_admin_unread_counts(queryset):
    return queryset.annotate(
        customer_unread_count=Count(
            'messages',
            filter=(
                Q(messages__sender_type__in=['admin', 'agent'])
                & (
                    Q(customer_last_read_at__isnull=True)
                    | Q(messages__timestamp__gt=models.F('customer_last_read_at'))
                )
            ),
        ),
        admin_unread_count=Count(
            'messages',
            filter=(
                Q(messages__sender_type='customer')
                & (
                    Q(admin_last_read_at__isnull=True)
                    | Q(messages__timestamp__gt=models.F('admin_last_read_at'))
                )
            ),
        ),
    )

# --- Serializers for Admin ---
class AgentSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentSettings
        fields = '__all__'

class AgentActionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentActionRequest
        fields = '__all__'

class CommissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commission
        fields = '__all__'

class StorePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StorePayment
        fields = '__all__'

class AdminNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminNotification
        fields = '__all__'

# --- Views ---
class AdminSupplierViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer

class AdminNotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    queryset = AdminNotification.objects.all().order_by('-created_at')
    serializer_class = AdminNotificationSerializer

    @action(detail=True, methods=['patch'])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response(AdminNotificationSerializer(notification).data)
class DashboardStatsView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        total_orders = Order.objects.count()
        total_revenue = Order.objects.aggregate(total=Sum('total_price'))['total'] or 0
        total_commissions = Commission.objects.aggregate(total=Sum('amount'))['total'] or 0
        received_commissions = Commission.objects.filter(is_settled=True).aggregate(total=Sum('amount'))['total'] or 0
        pending_commissions = Commission.objects.filter(is_settled=False).aggregate(total=Sum('amount'))['total'] or 0
        total_payments = StorePayment.objects.aggregate(total=Sum('amount'))['total'] or 0
        net_profit = received_commissions - total_payments
        total_products = Product.objects.filter(is_available=True).count()
        chat_stats = ChatConversation.objects.aggregate(
            total=Count('id'),
            needs_admin=Count('id', filter=Q(status='needs_admin')),
            open=Count('id', filter=Q(status='open')),
        )
        
        return Response({
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "total_commissions": total_commissions,
            "received_commissions": received_commissions,
            "pending_commissions": pending_commissions,
            "our_payments": total_payments,
            "net_profit": net_profit,
            "active_products": total_products,
            "chat_stats": chat_stats,
        })

class ChatAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    queryset = ChatConversation.objects.all().order_by('-last_message_at')
    serializer_class = ChatConversationSerializer

    def get_queryset(self):
        qs = with_admin_unread_counts(super().get_queryset())
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    @action(detail=True, methods=['patch'])
    def mark_read(self, request, pk=None):
        conversation = self.get_object()
        conversation.admin_last_read_at = timezone.now()
        conversation.save(update_fields=['admin_last_read_at', 'last_message_at'])
        return Response(ChatConversationSerializer(conversation).data)

    @action(detail=True, methods=['patch'])
    def activate_agent(self, request, pk=None):
        conversation = self.get_object()
        conversation.is_agent_active = True
        conversation.status = 'open'
        conversation.escalation_note = ''
        conversation.save(
            update_fields=[
                'is_agent_active',
                'status',
                'escalation_note',
                'last_message_at',
            ]
        )
        return Response(ChatConversationSerializer(conversation).data)

class ChatAdminReplyView(views.APIView):
    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk):
        conversation = get_object_or_404(ChatConversation, pk=pk)
        content = (request.data.get('content') or request.data.get('message') or '').strip()
        images = request.FILES.getlist('images')
        if not content and not images:
            return Response({"error": "content or images required"}, status=status.HTTP_400_BAD_REQUEST)
        
        msg = ChatMessage.objects.create(
            conversation=conversation,
            sender_type='admin',
            content=content
        )
        for image_file in images:
            ChatAttachment.objects.create(message=msg, image=image_file)
        # Update conversation status if it was needs_admin
        if conversation.status == 'needs_admin':
            conversation.status = 'open'
            conversation.save()

        from chat.notifications import send_customer_message_notification

        send_customer_message_notification(
            conversation.customer_identifier,
            content or 'صورة جديدة من خدمة العملاء',
        )
            
        data = ChatMessageSerializer(msg, context={"request": request}).data
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    "type": "chat_message",
                    "id": data["id"],
                    "message": data["content"],
                    "sender_type": data["sender_type"],
                    "timestamp": data["timestamp"],
                    "attachments": data["attachments"],
                },
            )

        return Response(data)

class AgentSettingsView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        settings = AgentSettings.load()
        return Response(AgentSettingsSerializer(settings).data)

    def patch(self, request):
        settings = AgentSettings.load()
        serializer = AgentSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AgentProductImageView(views.APIView):
    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        files = request.FILES.getlist('images')
        if not files:
            return Response({"detail": "images are required"}, status=status.HTTP_400_BAD_REQUEST)

        image_urls = []
        for image_file in files:
            safe_name = slugify(image_file.name.rsplit('.', 1)[0]) or 'product-image'
            extension = image_file.name.rsplit('.', 1)[-1] if '.' in image_file.name else 'jpg'
            path = default_storage.save(
                f"agent_uploads/{safe_name}-{uuid.uuid4().hex[:8]}.{extension}",
                image_file,
            )
            url = default_storage.url(path)
            image_urls.append(url if url.startswith('http') else request.build_absolute_uri(url))

        admin_text = request.data.get('message') or (
            "أنا الأدمن. اقرأ صور المنتج المرفوعة، استخرج بيانات المنتج، "
            "ولو البيانات كافية جهز طلب إضافة منتج للموافقة."
        )

        reply = async_to_sync(get_admin_reply)(
            history_messages=[],
            admin_message=admin_text,
            image_urls=image_urls,
        )

        return Response({
            "message": reply,
            "image_urls": image_urls,
        }, status=status.HTTP_201_CREATED)


class AgentProductDraftView(views.APIView):
    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]

    def _store_files(self, request, field_name):
        urls = []
        for image_file in request.FILES.getlist(field_name):
            safe_name = slugify(image_file.name.rsplit('.', 1)[0]) or field_name
            extension = image_file.name.rsplit('.', 1)[-1] if '.' in image_file.name else 'jpg'
            path = default_storage.save(
                f"agent_uploads/{safe_name}-{uuid.uuid4().hex[:8]}.{extension}",
                image_file,
            )
            url = default_storage.url(path)
            urls.append(url if url.startswith('http') else request.build_absolute_uri(url))
        return urls

    def post(self, request):
        source_text = request.data.get('source_text', '')
        previous_payload_raw = request.data.get('previous_payload') or '{}'
        send_for_approval = str(request.data.get('send_for_approval', '')).lower() in ('1', 'true', 'yes')

        try:
            previous_payload = json.loads(previous_payload_raw) if previous_payload_raw else {}
        except Exception:
            previous_payload = {}

        source_image_urls = self._store_files(request, 'source_files')
        product_image_urls = self._store_files(request, 'product_images')

        has_new_source = bool(source_text.strip() or source_image_urls)
        if previous_payload and not has_new_source:
            data = previous_payload
        elif has_new_source:
            data = extract_product_data(
                raw_text=source_text,
                image_urls=source_image_urls,
                previous_payload=previous_payload,
                correction_text=source_text if previous_payload else None,
            )
        else:
            return Response(
                {"detail": "source_text or source_files are required for extraction"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if product_image_urls:
            data['images'] = [
                {'url': url, 'is_primary': index == 0}
                for index, url in enumerate(product_image_urls)
            ]

        missing_fields = [field for field in REQUIRED_FIELDS if not data.get(field)]
        data['missing_fields'] = missing_fields
        data['ready_for_approval'] = len(missing_fields) == 0

        action_id = None
        if send_for_approval:
            if data.get('ready_for_approval'):
                action = AgentActionRequest.objects.create(
                    action_type='add_product',
                    payload=data,
                    reason='طلب إضافة منتج من شات الأدمن في الموقع',
                    status='pending',
                )
                action_id = str(action.id)
                message = 'Draft is ready and approval request was sent.'
            else:
                message = 'Draft still has missing fields. Complete them before approval.'
        elif data.get('ready_for_approval'):
            message = 'Draft is ready. Review it, then send it for approval.'
        else:
            missing = ', '.join(data.get('missing_fields', []))
            message = f'Draft needs more details: {missing}'

        return Response({
            'message': message,
            'draft': data,
            'action_id': action_id,
            'source_image_urls': source_image_urls,
            'product_image_urls': product_image_urls,
        }, status=status.HTTP_200_OK)

class AgentActionRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    queryset = AgentActionRequest.objects.all().order_by('-requested_at')
    serializer_class = AgentActionRequestSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    @action(detail=True, methods=['patch'])
    def approve(self, request, pk=None):
        from telegram_bot.agent_handlers import handle_agent_action_approval
        result = handle_agent_action_approval(str(pk))
        return Response({"result": result})

    @action(detail=True, methods=['patch'])
    def reject(self, request, pk=None):
        from telegram_bot.agent_handlers import handle_agent_action_rejection
        result = handle_agent_action_rejection(str(pk))
        return Response({"result": result})

class CommissionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    queryset = Commission.objects.all()
    serializer_class = CommissionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        settled = self.request.query_params.get('settled')
        if settled is not None:
            qs = qs.filter(is_settled=(settled.lower() == 'true'))
        return qs

    @action(detail=True, methods=['patch'])
    def settle(self, request, pk=None):
        commission = self.get_object()
        commission.is_settled = True
        commission.settled_at = timezone.now()
        commission.save()
        return Response(CommissionSerializer(commission).data)

    @action(detail=False, methods=['get'])
    def report(self, request):
        month = request.query_params.get('month')
        qs = self.get_queryset()
        if month:
            qs = qs.filter(order__created_at__month=month)
        
        total = qs.aggregate(total=Sum('amount'))['total'] or 0
        settled = qs.filter(is_settled=True).aggregate(total=Sum('amount'))['total'] or 0
        unsettled = qs.filter(is_settled=False).aggregate(total=Sum('amount'))['total'] or 0
        
        return Response({
            "total_commissions": total,
            "settled_commissions": settled,
            "unsettled_commissions": unsettled
        })


class StorePaymentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    queryset = StorePayment.objects.all()
    serializer_class = StorePaymentSerializer
