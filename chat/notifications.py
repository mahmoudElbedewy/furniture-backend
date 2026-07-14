import requests
from django.conf import settings

NTFY_TOPIC = getattr(settings, "NTFY_TOPIC", "furniture_alert_messages")
NTFY_AUTH_TOKEN = getattr(settings, "NTFY_AUTH_TOKEN", "")


def send_ntfy_alert(title: str, message: str, click_url: str = None):
    try:
        headers = {"Title": title.encode("utf-8")}
        if click_url:
            headers["Click"] = click_url
        if NTFY_AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {NTFY_AUTH_TOKEN}"
        r = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        print(f"ntfy alert sent, status={r.status_code}, response={r.text}")
    except Exception as e:
        print(f"ntfy alert failed: {e}")