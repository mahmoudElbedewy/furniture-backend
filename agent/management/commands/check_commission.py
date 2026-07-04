from django.core.management.base import BaseCommand
from agent.models import AgentActionRequest

class Command(BaseCommand):
    help = 'Check commission values in recent agent action requests'

    def handle(self, *args, **options):
        recent_requests = AgentActionRequest.objects.filter(action_type='add_product').order_by('-created_at')[:5]

        self.stdout.write("Recent Agent Action Requests:")
        for req in recent_requests:
            self.stdout.write(f"\nID: {req.id}")
            self.stdout.write(f"Status: {req.status}")
            self.stdout.write(f"Created: {req.created_at}")
            self.stdout.write(f"Commission value from payload: {req.payload.get('commission_value')}")
            self.stdout.write(f"Commission value type: {type(req.payload.get('commission_value'))}")
            self.stdout.write(f"Full payload keys: {req.payload.keys()}")
