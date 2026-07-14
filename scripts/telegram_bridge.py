import os
import json
import requests

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_ADMIN_CHAT_ID = os.environ["TELEGRAM_ADMIN_CHAT_ID"]
DJANGO_BASE_URL = os.environ["DJANGO_BASE_URL"].rstrip("/")
BRIDGE_SECRET = os.environ["BRIDGE_SECRET"]

HEADERS = {"X-Bridge-Secret": BRIDGE_SECRET}
TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
BRIDGE_API = f"{DJANGO_BASE_URL}/api/telegram/bridge"


def send_pending_notifications():
    resp = requests.get(f"{BRIDGE_API}/pending/", headers=HEADERS, timeout=20)
    resp.raise_for_status()
    items = resp.json().get("results", [])

    for item in items:
        payload = {
            "chat_id": TELEGRAM_ADMIN_CHAT_ID,
            "text": item["message"],
            "parse_mode": "HTML",
        }
        if item.get("buttons"):
            payload["reply_markup"] = json.dumps({"inline_keyboard": [item["buttons"]]})

        r = requests.post(f"{TG_API}/sendMessage", data=payload, timeout=20)
        ok = r.status_code == 200
        if not ok:
            print(f"sendMessage failed for notification {item['id']}: {r.text}")

        requests.post(
            f"{BRIDGE_API}/mark-sent/{item['id']}/",
            headers=HEADERS,
            json={"sent": ok},
            timeout=20,
        )
        print(f"notification {item['id']} sent={ok}")


def process_telegram_updates():
    offset_resp = requests.get(f"{BRIDGE_API}/offset/", headers=HEADERS, timeout=20)
    offset_resp.raise_for_status()
    offset = offset_resp.json().get("offset")

    params = {"timeout": 5}
    if offset:
        params["offset"] = offset

    r = requests.get(f"{TG_API}/getUpdates", params=params, timeout=15)
    data = r.json()
    if not data.get("ok"):
        print(f"getUpdates error: {data}")
        return

    new_offset = offset
    for update in data.get("result", []):
        new_offset = update["update_id"] + 1
        callback_query = update.get("callback_query")
        if not callback_query:
            continue

        callback_data = callback_query["data"]
        callback_id = callback_query["id"]
        result_text = "أمر غير معروف"

        if callback_data.startswith("order_approve:"):
            order_number = callback_data.split(":", 1)[1]
            action_resp = requests.post(
                f"{BRIDGE_API}/approve/{order_number}/", headers=HEADERS, timeout=20
            )
            result_text = (
                action_resp.json().get("result", "تم")
                if action_resp.status_code == 200
                else "حصل خطأ"
            )

        elif callback_data.startswith("order_reject:"):
            order_number = callback_data.split(":", 1)[1]
            action_resp = requests.post(
                f"{BRIDGE_API}/reject/{order_number}/", headers=HEADERS, timeout=20
            )
            result_text = (
                action_resp.json().get("result", "تم")
                if action_resp.status_code == 200
                else "حصل خطأ"
            )
        elif callback_data.startswith("order_reject:"):
            order_number = callback_data.split(":", 1)[1]
            action_resp = requests.post(
                f"{BRIDGE_API}/reject/{order_number}/", headers=HEADERS, timeout=20
            )
            result_text = (
                action_resp.json().get("result", "تم")
                if action_resp.status_code == 200
                else "حصل خطأ"
            )

        elif callback_data.startswith("agent_approve:"):
            req_id = callback_data.split(":", 1)[1]
            action_resp = requests.post(
                f"{BRIDGE_API}/agent-approve/{req_id}/", headers=HEADERS, timeout=20
            )
            result_text = (
                action_resp.json().get("result", "تم")
                if action_resp.status_code == 200
                else "حصل خطأ"
            )

        elif callback_data.startswith("agent_reject:"):
            req_id = callback_data.split(":", 1)[1]
            action_resp = requests.post(
                f"{BRIDGE_API}/agent-reject/{req_id}/", headers=HEADERS, timeout=20
            )
            result_text = (
                action_resp.json().get("result", "تم")
                if action_resp.status_code == 200
                else "حصل خطأ"
            )
        requests.post(
            f"{TG_API}/answerCallbackQuery",
            data={"callback_query_id": callback_id, "text": result_text},
            timeout=15,
        )
        requests.post(
            f"{TG_API}/editMessageText",
            data={
                "chat_id": callback_query["message"]["chat"]["id"],
                "message_id": callback_query["message"]["message_id"],
                "text": callback_query["message"]["text"] + f"\n\n{result_text}",
            },
            timeout=15,
        )
        print(f"processed callback '{callback_data}' -> {result_text}")

    if new_offset != offset:
        requests.post(
            f"{BRIDGE_API}/offset/",
            headers=HEADERS,
            json={"offset": new_offset},
            timeout=20,
        )


import time


def run_once():
    try:
        send_pending_notifications()
    except Exception as e:
        print(f"send_pending_notifications failed: {e}")

    try:
        process_telegram_updates()
    except Exception as e:
        print(f"process_telegram_updates failed: {e}")


if __name__ == "__main__":
    start_time = time.time()
    loop_duration = 280  # Run for 280 seconds (just under 5 minutes)
    interval = 15  # Check every 15 seconds

    print("Starting Telegram Bridge loop...")
    while time.time() - start_time < loop_duration:
        loop_start = time.time()
        
        run_once()
        
        elapsed = time.time() - loop_start
        sleep_time = max(0, interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)
    print("Bridge loop finished successfully.")
