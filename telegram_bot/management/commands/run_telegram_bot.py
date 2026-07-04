import time
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from telegram_bot.handlers import handle_order_approval, handle_order_rejection


class Command(BaseCommand):
    help = "يشغّل بوت تليجرام في وضع Polling لاستقبال ضغطات أزرار الموافقة/الرفض"

    def handle(self, *args, **options):
        token = settings.TELEGRAM_BOT_TOKEN
        base_url = f"https://api.telegram.org/bot{token}"
        offset = None

        self.stdout.write(self.style.SUCCESS("بوت التليجرام شغال... (Polling)"))

        while True:
            try:
                params = {"timeout": 30}
                if offset:
                    params["offset"] = offset

                response = requests.get(
                    f"{base_url}/getUpdates", params=params, timeout=35
                )
                data = response.json()

                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    callback_query = update.get("callback_query")
                    if not callback_query:
                        continue

                    callback_data = callback_query["data"]
                    callback_id = callback_query["id"]

                    sender_chat_id = str(callback_query["message"]["chat"]["id"])
                    if sender_chat_id != str(settings.TELEGRAM_ADMIN_CHAT_ID):
                        requests.post(
                            f"{base_url}/answerCallbackQuery",
                            data={
                                "callback_query_id": callback_id,
                                "text": "غير مصرح",
                            },
                        )
                        continue

                    if callback_data.startswith("order_approve:"):
                        order_number = callback_data.split(":", 1)[1]
                        result_text = handle_order_approval(order_number)

                    elif callback_data.startswith("order_reject:"):
                        order_number = callback_data.split(":", 1)[1]
                        result_text = handle_order_rejection(order_number)
                        
                    elif callback_data.startswith("agent_approve:"):
                        req_id = callback_data.split(":", 1)[1]
                        from telegram_bot.agent_handlers import handle_agent_action_approval
                        result_text = handle_agent_action_approval(req_id)

                    elif callback_data.startswith("agent_reject:"):
                        req_id = callback_data.split(":", 1)[1]
                        from telegram_bot.agent_handlers import handle_agent_action_rejection
                        result_text = handle_agent_action_rejection(req_id)

                    else:
                        result_text = "أمر غير معروف"

                    requests.post(
                        f"{base_url}/answerCallbackQuery",
                        data={
                            "callback_query_id": callback_id,
                            "text": result_text,
                        },
                    )

                    requests.post(
                        f"{base_url}/editMessageText",
                        data={
                            "chat_id": callback_query["message"]["chat"]["id"],
                            "message_id": callback_query["message"]["message_id"],
                            "text": callback_query["message"]["text"]
                            + f"\n\n{result_text}",
                        },
                    )

            except requests.RequestException as e:
                self.stdout.write(self.style.WARNING(f"خطأ مؤقت في الاتصال: {e}"))
                time.sleep(5)
