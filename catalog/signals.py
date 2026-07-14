from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Product, Category, Governorate


@receiver([post_save, post_delete], sender=Product)
def invalidate_catalog_cache(sender, **kwargs):
    cache.delete("agent_catalog_summary_v1")


@receiver([post_save, post_delete], sender=Category)
def invalidate_category_keywords_cache(sender, **kwargs):
    cache.delete("agent_category_keywords_v1")


@receiver([post_save, post_delete], sender=Governorate)
def invalidate_governorate_cache(sender, **kwargs):
    cache.delete("agent_governorate_names_v1")