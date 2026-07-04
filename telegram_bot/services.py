import time
import ssl
import requests
from requests.adapters import HTTPAdapter
from django.conf import settings
from .models import AdminNotification


class _EOFTolerantAdapter(HTTPAdapter):
    """
    يحل مشكلة SSLEOFError (UNEXPECTED_EOF_WHILE_READING) المعروفة بين
    Python 3.10/3.11 + urllib3 2.x + OpenSSL 3.0، عن طريق تفعيل
    SSL_OP_IGNORE_UNEXPECTED_EOF على الـ SSL context.
    """

    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        # OP_IGNORE_UNEXPECTED_EOF متاح من Python 3.8+ / OpenSSL 3.0+
        if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
            context.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)


_session = requests.Session()
_session.mount("https://", _EOFTolerantAdapter())


def _telegram_url(method: str) -> str:
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
            response = _session.post(url, data=payload, headers=headers, timeout=timeout)
            if response.status_code != 200:
                print(f"Telegram request failed [{response.status_code}]: {response.text}")
            return response
        except requests.exceptions.ReadTimeout as e:
            last_error = e
            print(f"Telegram request timed out (attempt {attempt + 1}/{retries + 1})")
            time.sleep(1)
        except requests.RequestException as e:
            last_error = e
            print(f"Telegram request error: {e}")
            time.sleep(1)
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