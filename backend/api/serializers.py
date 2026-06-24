from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, Item, Negotiation, NegotiationMessage

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['phone_number', 'location']

class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'profile']

class ItemSerializer(serializers.ModelSerializer):
    seller = UserSerializer(read_only=True)
    
    class Meta:
        model = Item
        fields = [
            'id', 'seller', 'title', 'category', 'quoted_price', 
            'min_price', 'seller_strategy', 'description', 
            'image_url', 'status', 'created_at'
        ]
        extra_kwargs = {
            'min_price': {'write_only': True}  # Enforce min_price is hidden from client GET requests
        }

class NegotiationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = NegotiationMessage
        fields = ['id', 'sender', 'content', 'price_offered', 'timestamp']

class NegotiationSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    buyer = UserSerializer(read_only=True)
    messages = NegotiationMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Negotiation
        fields = [
            'id', 'item', 'buyer', 'buyer_max_budget', 
            'buyer_strategy', 'status', 'agreed_price', 
            'created_at', 'updated_at', 'messages'
        ]
        extra_kwargs = {
            'buyer_max_budget': {'write_only': True}  # Enforce buyer_max_budget is hidden from client GET requests
        }

