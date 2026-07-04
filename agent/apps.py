from django.apps import AppConfig


class AgentConfig(AppConfig):
    name = 'agent'
    def ready(self):
        import catalog.signals
