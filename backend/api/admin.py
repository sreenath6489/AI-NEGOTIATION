from django.contrib import admin
from .models import UserProfile, Item, Negotiation, NegotiationMessage

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone_number', 'location']
    search_fields = ['user__username', 'location']

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'seller', 'quoted_price', 'min_price', 'seller_strategy', 'status', 'created_at']
    list_filter = ['status', 'category', 'seller_strategy']
    search_fields = ['title', 'description', 'seller__username']

class NegotiationMessageInline(admin.TabularInline):
    model = NegotiationMessage
    extra = 0
    readonly_fields = ['sender', 'content', 'price_offered', 'timestamp']

@admin.register(Negotiation)
class NegotiationAdmin(admin.ModelAdmin):
    list_display = ['item', 'buyer', 'buyer_max_budget', 'buyer_strategy', 'status', 'agreed_price', 'created_at']
    list_filter = ['status', 'buyer_strategy']
    search_fields = ['item__title', 'buyer__username']
    inlines = [NegotiationMessageInline]

@admin.register(NegotiationMessage)
class NegotiationMessageAdmin(admin.ModelAdmin):
    list_display = ['negotiation', 'sender', 'price_offered', 'timestamp']
    list_filter = ['sender']
    search_fields = ['negotiation__item__title', 'content']

