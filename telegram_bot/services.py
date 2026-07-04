import time
import requests
from django.conf import settings
from .models import AdminNotification


def _telegram_url(method: str) -> str:
    """
    بيبني الرابط: لو فيه relay مظبوط بيستخدمه، لو مفيش بيرجع لتليجرام مباشرة
    (fallback عشان الكود يفضل شغال حتى لو الـ relay اتشال يوم من الأيام).
    """
    if settings.TELEGRAM_RELAY_BASE_URL:
        return f"{settings.TELEGRAM_RELAY_BASE_URL}/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
    return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


def _relay_headers() -> dict:
    if settings.TELEGRAM_RELAY_BASE_URL and settings.TELEGRAM_RELAY_SECRET:
        return {"X-Relay-Secret": settings.TELEGRAM_RELAY_SECRET}
    return {}


def _post_with_retry(url, payload, headers=None, timeout=15, retries=1):
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=timeout)
            if response.status_code != 200:
                print(f"Telegram request failed [{response.status_code}]: {response.text}")
            return response
        except requests.exceptions.ReadTimeout as e:
            last_error = e
            print(f"Telegram request timed out (attempt {attempt + 1}/{retries + 1})")
            time.sleep(1)
        except requests.RequestException as e:
            print(f"Telegram request error: {e}")
            return None
    print(f"Telegram request failed after retries: {last_error}")
    return None


def send_telegram_message(text: str) -> bool:
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ADMIN_CHAT_ID:
        print("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_ADMIN_CHAT_ID is missing.")
        return False

    url = _telegram_url("sendMessage")
    payload = {
        "chat_id": settings.TELEGRAM_ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    response = _post_with_retry(url, payload, headers=_relay_headers())
    return response is not None and response.status_code == 200


def send_telegram_message_with_buttons(text: str, buttons: list) -> bool:
    """
    buttons مثال:
    [{"text": "✅ موافقة", "callback_data": "order_approve:ORD-XXXX"},
     {"text": "❌ رفض", "callback_data": "order_reject:ORD-XXXX"}]
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ADMIN_CHAT_ID:
        print("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_ADMIN_CHAT_ID is missing.")
        return False

    import json

    url = _telegram_url("sendMessage")
    payload = {
        "chat_id": settings.TELEGRAM_ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps({"inline_keyboard": [buttons]}),
    }
    response = _post_with_retry(url, payload, headers=_relay_headers())
    return response is not None and response.status_code == 200


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