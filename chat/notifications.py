import requests

NTFY_TOPIC = "furniture_alert_messages"


def send_ntfy_alert(title: str, message: str, click_url: str = None):
    """يبعت إشعار فوري على الموبايل عن طريق ntfy.sh"""
    try:
        headers = {"Title": title.encode("utf-8")}
        if click_url:
            headers["Click"] = click_url
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
    except Exception as e:
        print(f"ntfy alert failed: {e}")