from django.utils import timezone
from orders.models import Order, OrderStatusLog
from chat.models import ChatConversation, ChatMessage

def handle_order_approval(order_number: str):
    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        return "❌ الأوردر مش موجود."

    old_status = order.status
    order.status = 'supplier_confirmed'
    order.save()

    OrderStatusLog.objects.create(
        order=order, old_status=old_status, new_status='supplier_confirmed', changed_by='admin'
    )

    _notify_customer_chat(order, "تم تأكيد أوردرك وجاري التجهيز للتوصيل. 🚚")

    return f"✅ تم تأكيد الأوردر {order.order_number}"

def handle_order_rejection(order_number: str):
    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        return "❌ الأوردر مش موجود."

    old_status = order.status
    order.status = 'cancelled'
    order.save()

    OrderStatusLog.objects.create(
        order=order, old_status=old_status, new_status='cancelled', changed_by='admin'
    )

    _notify_customer_chat(order, "نعتذر، تم إلغاء أوردرك . للتواصل معنا للاستفسار.")

    return f"❌ تم رفض الأوردر {order.order_number}"

def _notify_customer_chat(order, text):
    """يكتب رسالة في شات العميل لو عنده محادثة مفتوحة على نفس رقم تليفونه."""
    conversation = ChatConversation.objects.filter(
        customer_identifier=order.customer_phone
    ).order_by('-last_message_at').first()

    if conversation:
        ChatMessage.objects.create(
            conversation=conversation,
            sender_type='admin',
            content=text,
        )
        conversation.save() 