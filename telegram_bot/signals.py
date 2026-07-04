from django.db.models.signals import post_save
from django.dispatch import receiver

from orders.models import Order
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from chat.models import ChatConversation, ChatMessage
from agent.models import AgentActionRequest, AgentSettings

from .services import notify_admin


# Disabled - notification moved to OrderSerializer to ensure items are loaded
# @receiver(post_save, sender=Order)
# def notify_new_order(sender, instance, created, **kwargs):
#     if not created:
#         return
#
#     # Reload the order from database to get the items
#     try:
#         order = Order.objects.get(id=instance.id)
#     except Order.DoesNotExist:
#         return
#
#     lines = []
#     for item in order.items.all():
#         product = item.product
#         base = product.base_price
#         commission = product.commission_value
#         after_commission = item.price_at_order_time
#
#         lines.append(
#             f"- {product.title} x{item.quantity}\n"
#             f"  السعر قبل العمولة: {base} ج\n"
#             f"  العمولة: {commission} ج\n"
#             f"  السعر بعد العمولة: {after_commission} ج"
#         )
#
#     items_text = "\n".join(lines) or "لا توجد عناصر بعد"
#
#     message = (
#         f"🛒 <b>أوردر جديد</b>\n"
#         f"رقم الأوردر: {order.order_number}\n"
#         f"العميل: {order.customer_name} ({order.customer_phone})\n"
#         f"المحافظة: {order.customer_governorate}"
#         + (f" - {order.customer_area}" if order.customer_area else "")
#         + "\n"
#         f"العنوان: {order.customer_address}\n"
#         f"المنتجات:\n{items_text}\n"
#         f"تكلفة الشحن: {order.shipping_price} ج\n"
#         f"الإجمالي: {order.total_price} ج"
#     )
#     buttons = [
#         {
#             "text": "✅ موافقة",
#             "callback_data": f"order_approve:{order.order_number}",
#         },
#         {
#             "text": "❌ رفض",
#             "callback_data": f"order_reject:{order.order_number}",
#         },
#     ]
#
#     notify_admin("new_order", order.id, message, buttons=buttons)


@receiver(post_save, sender=ChatConversation)
def notify_chat_needs_admin(sender, instance, created, **kwargs):
    if instance.status != "needs_admin":
        return

    message = (
        f"💬 <b>محادثة محتاجة تدخّل أدمن</b>\n"
        f"العميل: {instance.customer_name or instance.customer_identifier}\n"
        f"رقم/معرّف العميل: {instance.customer_identifier}"
    )

    notify_admin("new_chat_message", instance.id, message)


@receiver(post_save, sender=ChatMessage)
def notify_manual_mode_customer_message(sender, instance, created, **kwargs):
    if not created:
        return

    conversation = instance.conversation

    if instance.sender_type == "admin":
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    "type": "chat_message",
                    "message": instance.content,
                    "sender_type": "admin",
                    "timestamp": instance.timestamp.isoformat(),
                    "metadata": {},
                },
            )
        return

    if instance.sender_type != "customer":
        return

    settings = AgentSettings.load()
    auto_is_effective = (
        conversation.force_agent_auto
        or (
            conversation.is_agent_active
            and settings.is_globally_active
            and settings.auto_reply_mode == "full_auto"
        )
    )
    if auto_is_effective:
        return

    message = (
        "💬 <b>رسالة عميل جديدة والرد اليدوي شغال</b>\n"
        f"العميل: {conversation.customer_name or conversation.customer_identifier}\n"
        f"رقم/معرّف العميل: {conversation.customer_identifier}\n"
        f"الرسالة: {instance.content}"
    )
    notify_admin("new_chat_message", conversation.id, message)


@receiver(post_save, sender=AgentActionRequest)
def notify_agent_action_request(sender, instance, created, **kwargs):
    if not created:
        return

    import json

    # تحسين عرض الـ payload
    try:
        payload_text = json.dumps(instance.payload, ensure_ascii=False, indent=2)
    except:
        payload_text = str(instance.payload)

    message = (
        f"🤖 <b>طلب موافقة من الإيجنت</b>\n"
        f"النوع: {instance.get_action_type_display()}\n"
        f"التفاصيل:\n<pre>{payload_text}</pre>\n"
        f"السبب: {instance.reason or '—'}\n"
    )

    buttons = [
        {"text": "✅ موافقة وإضافة", "callback_data": f"agent_approve:{instance.id}"},
        {"text": "❌ رفض", "callback_data": f"agent_reject:{instance.id}"},
    ]

    notify_admin("agent_action_request", instance.id, message, buttons=buttons)
