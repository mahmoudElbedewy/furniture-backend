from django.core.management.base import BaseCommand
from agent.analytics_sync import sync_all


class Command(BaseCommand):
    help = 'Pulls Meta + GA4 metrics into local DB tables (run every 15-60 min via cron / GitHub Actions)'

    def handle(self, *args, **options):
        results = sync_all()
        for source, result in results.items():
            if result.get('ok'):
                self.stdout.write(self.style.SUCCESS(f'{source}: synced ✅'))
            else:
                self.stdout.write(self.style.WARNING(f'{source}: {result.get("error")}'))