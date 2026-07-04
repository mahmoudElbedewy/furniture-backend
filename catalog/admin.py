from django.contrib import admin
from .models import Category, Governorate, Area, Product, ProductImage, ProductShippingRate, Review


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(Governorate)
class GovernorateAdmin(admin.ModelAdmin):
    list_display = ('name', 'region')
    list_filter = ('region',)
    search_fields = ('name',)


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'governorate')
    list_filter = ('governorate',)
    search_fields = ('name',)
    autocomplete_fields = ('governorate',)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductShippingRateInline(admin.TabularInline):
    model = ProductShippingRate
    extra = 1
    autocomplete_fields = ('governorate', 'area')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'supplier', 'category', 'base_price', 'commission_value', 'final_price', 'requires_deposit', 'deposit_amount', 'is_available', 'created_at')
    list_filter = ('is_available', 'ships_nationwide', 'requires_deposit', 'category', 'supplier')
    search_fields = ('title', 'description', 'material', 'color', 'source_raw_text')
    prepopulated_fields = {'slug': ('title',)}
    autocomplete_fields = ('supplier', 'category')
    readonly_fields = ('final_price', 'views_count', 'orders_count', 'created_at', 'updated_at')
    inlines = (ProductImageInline, ProductShippingRateInline)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'customer_name', 'rating', 'is_verified_purchase', 'created_at')
    list_filter = ('rating', 'is_verified_purchase')
    search_fields = ('customer_name', 'comment')
    autocomplete_fields = ('product',)