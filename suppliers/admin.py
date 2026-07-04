from django.contrib import admin
from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('channel_name', 'contact_person', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('channel_name', 'contact_person')