import requests
from django.conf import settings
from .models import AdminNotification


def send_telegram_message(text: str) -> bool:
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ADMIN_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False


def send_telegram_message_with_buttons(text: str, buttons: list) -> bool:
    """
    buttons مثال:
    [{"text": "✅ موافقة", "callback_data": "order_approve:ORD-XXXX"},
     {"text": "❌ رفض", "callback_data": "order_reject:ORD-XXXX"}]
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ADMIN_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [buttons]},
    }
    try:
        import json

        payload["reply_markup"] = json.dumps(payload["reply_markup"])
        response = requests.post(url, data=payload, timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False


def notify_admin(
    notification_type: str, related_object_id: str, message: str, buttons: list = None
) -> AdminNotification:
    """
    يعمل سطر في AdminNotification ويحاول يبعت الإشعار فعليًا على تليجرام.
    """
    if buttons:
        sent = send_telegram_message_with_buttons(message, buttons)
    else:
        sent = send_telegram_message(message)

    notification = AdminNotification.objects.create(
        type=notification_type,
        related_object_id=str(related_object_id),
        message=message,
        sent_via_telegram=sent,
    )
    return notification
