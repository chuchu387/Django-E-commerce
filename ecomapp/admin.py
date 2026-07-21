from django.contrib import admin
from .models import *


class ProductAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "vendor", "selling_price", "stock", "is_approved", "is_available", "is_hidden", "view_count"]
    list_filter = ["is_approved", "is_available", "is_hidden", "category", "vendor"]
    search_fields = ["title", "description"]
    list_editable = ["is_approved", "is_available", "is_hidden", "stock"]


class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "ordered_by", "order_status", "total", "platform_commission", "delivery_zone", "payment_method", "payment_completed", "cancellation_requested", "refund_status", "created_at"]
    list_filter = ["order_status", "payment_method", "payment_completed", "delivery_zone", "refund_status"]
    search_fields = ["ordered_by", "shipping_address", "mobile"]


class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ["name", "fee", "min_order_for_free_delivery", "is_active"]
    list_editable = ["fee", "is_active"]


class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "vendor", "discount_type", "discount_value", "min_order_amount", "used_count", "max_uses", "is_approved", "is_active"]
    list_editable = ["is_approved", "is_active"]
    list_filter = ["is_approved", "is_referral", "is_active", "vendor"]


class ReviewAdmin(admin.ModelAdmin):
    list_display = ["product", "customer", "rating", "is_approved", "created_at"]
    list_filter = ["is_approved", "rating"]
    list_editable = ["is_approved"]
    search_fields = ["product__title", "customer__full_name", "text"]


class VendorAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = ["name", "contact_email", "is_active", "created_at"]
    list_filter = ["is_active"]
    list_editable = ["is_active"]
    search_fields = ["name", "contact_email"]


class ReferralAdmin(admin.ModelAdmin):
    list_display = ["referrer", "referred", "coupon", "reward_given", "created_at"]
    list_filter = ["reward_given"]


admin.site.register([Admin, Customer, Category, Cart, CartProduct, ProductImage, Favorite])
admin.site.register(Address)
admin.site.register(Product, ProductAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(DeliveryZone, DeliveryZoneAdmin)
admin.site.register(Coupon, CouponAdmin)
admin.site.register(Review, ReviewAdmin)
admin.site.register(Vendor, VendorAdmin)
admin.site.register(Referral, ReferralAdmin)
admin.site.register(OrderStatusLog)
admin.site.register(CommissionConfig)
admin.site.register(VendorPayout)
