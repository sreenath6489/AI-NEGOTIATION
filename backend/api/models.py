from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

class Item(models.Model):
    CATEGORY_CHOICES = [
        ('Electronics', 'Electronics'),
        ('Furniture', 'Furniture'),
        ('Fashion', 'Fashion'),
        ('Vehicles', 'Vehicles'),
        ('Home Goods', 'Home Goods'),
        ('Sports', 'Sports'),
        ('Other', 'Other'),
    ]
    STRATEGY_CHOICES = [
        ('diplomat', 'The Diplomat (Win-win, cooperative)'),
        ('shark', 'The Shark (Aggressive, stubborn)'),
        ('frugal', 'The Frugal (Value-oriented, critical)'),
    ]
    
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings')
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=100, choices=CATEGORY_CHOICES)
    quoted_price = models.DecimalField(max_digits=10, decimal_places=2)
    min_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Minimum price seller is willing to accept (hidden from buyer)")
    seller_strategy = models.CharField(max_length=50, choices=STRATEGY_CHOICES, default='diplomat')
    description = models.TextField()
    image_url = models.URLField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=20, default='active', choices=[('active', 'Active'), ('sold', 'Sold')])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Negotiation(models.Model):
    STATUS_CHOICES = [
        ('negotiating', 'Negotiating'),
        ('agreed', 'Agreed'),
        ('failed', 'Failed'),
    ]
    
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='negotiations')
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='buyer_negotiations')
    buyer_max_budget = models.DecimalField(max_digits=10, decimal_places=2)
    buyer_strategy = models.CharField(max_length=50, choices=Item.STRATEGY_CHOICES, default='diplomat')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='negotiating')
    agreed_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Negotiation for {self.item.title} (Buyer: {self.buyer.username})"

class NegotiationMessage(models.Model):
    SENDER_CHOICES = [
        ('buyer_agent', 'Buyer Agent'),
        ('seller_agent', 'Seller Agent'),
        ('system', 'System Event'),
    ]
    
    negotiation = models.ForeignKey(Negotiation, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=20, choices=SENDER_CHOICES)
    content = models.TextField()
    price_offered = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender} @ {self.timestamp}"
