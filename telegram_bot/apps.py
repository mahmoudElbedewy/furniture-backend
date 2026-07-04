from django.apps import AppConfig


class TelegramBotConfig(AppConfig):
    name = 'telegram_bot'

    def ready(self):
        import telegram_bot.signals
