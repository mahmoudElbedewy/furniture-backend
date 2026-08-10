import json
import requests
from django.conf import settings
from .models import CustomerPushSubscription

NTFY_TOPIC = getattr(settings, "NTFY_TOPIC", "") or "furniture_alert_messages"
NTFY_AUTH_TOKEN = getattr(settings, "NTFY_AUTH_TOKEN", "")


def send_ntfy_alert(title: str, message: str, click_url: str = None):
    try:
        payload = {
            "topic": NTFY_TOPIC,
            "title": title,
            "message": message,
        }
        if click_url:
            payload["click"] = click_url
        headers = {}
        if NTFY_AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {NTFY_AUTH_TOKEN}"
        r = requests.post(
            "https://ntfy.sh",
            json=payload,
            headers=headers,
            timeout=10,
        )
        print(f"ntfy alert sent, status={r.status_code}, response={r.text}")
    except Exception as e:
        print(f"ntfy alert failed: {e}")


def send_customer_message_notification(customer_identifier: str, message: str):
    subscriptions = CustomerPushSubscription.objects.filter(
        customer_identifier=customer_identifier, is_active=True
    )
    if not subscriptions.exists():
        return

    vapid_private_key = getattr(settings, "WEB_PUSH_VAPID_PRIVATE_KEY", "")
    vapid_email = getattr(settings, "WEB_PUSH_VAPID_EMAIL", "")
    if not vapid_private_key or not vapid_email:
        print("web push skipped: VAPID settings are missing")
        return

    try:
        from pywebpush import WebPushException, webpush
    except Exception as exc:
        print(f"web push skipped: pywebpush is not installed ({exc})")
        return

    payload = {
        "title": "رسالة جديدة من خدمة العملاء",
        "body": message,
        "url": getattr(settings, "FRONTEND_BASE_URL", ""),
    }
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.p256dh,
                        "auth": subscription.auth,
                    },
                },
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": f"mailto:{vapid_email}"},
            )
        except WebPushException as exc:
            if getattr(exc.response, "status_code", None) in (404, 410):
                subscription.is_active = False
                subscription.save(update_fields=["is_active", "updated_at"])
            print(f"web push failed: {exc}")
