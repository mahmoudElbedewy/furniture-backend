import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from agent.models import AgentSettings, FacebookPostMetric, MetaPostCache  # noqa: E402


def clear_seed_data():
    deleted = {}
    deleted["facebook_post_metrics"] = FacebookPostMetric.objects.filter(
        post_id__startswith="fb_post_"
    ).delete()[0]
    deleted["meta_post_cache"] = MetaPostCache.objects.filter(
        post_id__startswith="fb_post_"
    ).delete()[0]

    settings = AgentSettings.load()
    changed = []
    if settings.fb_followers_override in (1250, 12500):
        settings.fb_followers_override = None
        changed.append("fb_followers_override")
    if settings.fb_reach_override in (4800, 45800):
        settings.fb_reach_override = None
        changed.append("fb_reach_override")
    if settings.ig_followers_override in (0, 8400):
        settings.ig_followers_override = None
        changed.append("ig_followers_override")
    if settings.ig_page_url == "https://instagram.com/dummy":
        settings.ig_page_url = ""
        changed.append("ig_page_url")
    if settings.is_meta_connected and not settings.meta_access_token:
        settings.is_meta_connected = False
        changed.append("is_meta_connected")
    if changed:
        settings.save(update_fields=changed)

    return deleted


if __name__ == "__main__":
    print("Analytics dummy seeding is disabled.")
    print("Removed seeded analytics rows:", clear_seed_data())
