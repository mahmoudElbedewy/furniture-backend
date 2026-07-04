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
        # Post-request timeout for answerCallbackQuery / editMessageText,
        # separate from the long-poll timeout used for getUpdates.
        post_timeout = 15

        self.stdout.write(self.style.SUCCESS("بوت التليجرام شغال... (Polling)"))

        while True:
            try:
                params = {"timeout": 30}
                if offset:
                    params["offset"] = offset

                response = requests.get(
                    f"{base_url}/getUpdates", params=params, timeout=(10, 40)
                )
                data = response.json()

                if not data.get("ok", False):
                    self.stdout.write(
                        self.style.WARNING(f"تليجرام رجّع خطأ: {data}")
                    )
                    time.sleep(5)
                    continue

                for update in data.get("result", []):
                    # Advance the offset immediately so a bad update never
                    # gets stuck retrying forever, then isolate everything
                    # else so one failure can't kill the whole loop.
                    offset = update["update_id"] + 1

                    try:
                        self._process_update(update, base_url, post_timeout)
                    except Exception as update_error:  # noqa: BLE001
                        self.stdout.write(
                            self.style.ERROR(
                                f"خطأ أثناء معالجة update {update.get('update_id')}: {update_error}"
                            )
                        )

            except requests.exceptions.ReadTimeout:
                continue
            except requests.RequestException as e:
                self.stdout.write(self.style.WARNING(f"خطأ مؤقت في الاتصال: {e}"))
                time.sleep(5)
            except Exception as loop_error:  # noqa: BLE001
                self.stdout.write(
                    self.style.ERROR(f"خطأ غير متوقع في اللوب الرئيسي: {loop_error}")
                )
                time.sleep(5)

    def _process_update(self, update, base_url, post_timeout):
        callback_query = update.get("callback_query")
        if not callback_query:
            return

        callback_data = callback_query["data"]
        callback_id = callback_query["id"]

        sender_chat_id = str(callback_query["message"]["chat"]["id"])
        if sender_chat_id != str(settings.TELEGRAM_ADMIN_CHAT_ID):
            requests.post(
                f"{base_url}/answerCallbackQuery",
                data={"callback_query_id": callback_id, "text": "غير مصرح"},
                timeout=post_timeout,
            )
            return

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
            data={"callback_query_id": callback_id, "text": result_text},
            timeout=post_timeout,
        )

        requests.post(
            f"{base_url}/editMessageText",
            data={
                "chat_id": callback_query["message"]["chat"]["id"],
                "message_id": callback_query["message"]["message_id"],
                "text": callback_query["message"]["text"] + f"\n\n{result_text}",
            },
            timeout=post_timeout,
        )