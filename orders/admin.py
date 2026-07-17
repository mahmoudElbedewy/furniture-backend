from django.contrib import admin
from .models import Order, OrderItem, OrderStatusLog, Commission, AbandonedCart


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ('product',)
    readonly_fields = ('price_at_order_time', 'variant_size_name')
    fields = ('product', 'variant', 'variant_size_name', 'quantity', 'price_at_order_time', 'shipping_price', 'shipping_location')


class OrderStatusLogInline(admin.TabularInline):
    model = OrderStatusLog
    extra = 0
    readonly_fields = ('old_status', 'new_status', 'changed_by', 'timestamp')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer_name', 'customer_phone', 'status', 'total_price', 'created_at')
    list_filter = ('status', 'customer_governorate')
    search_fields = ('order_number', 'customer_name', 'customer_phone')
    readonly_fields = ('order_number', 'created_at', 'updated_at')
    inlines = (OrderItemInline, OrderStatusLogInline)

    fieldsets = (
        ('بيانات الأوردر', {
            'fields': ('order_number', 'status', 'user')
        }),
        ('بيانات العميل', {
            'fields': ('customer_name', 'customer_phone', 'customer_governorate', 'customer_area', 'customer_address')
        }),
        ('التسعير', {
            'fields': ('shipping_price', 'total_price', 'notes')
        }),
        ('توقيتات', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ('order', 'amount', 'is_settled', 'settled_at')
    list_filter = ('is_settled',)
    search_fields = ('order__order_number',)
    autocomplete_fields = ('order',)


@admin.register(AbandonedCart)
class AbandonedCartAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'product', 'captured_at', 'converted_to_order')
    list_filter = ('converted_to_order',)
    search_fields = ('phone_number',)
    autocomplete_fields = ('product',)