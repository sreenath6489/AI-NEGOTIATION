from django.urls import path
from . import views

urlpatterns = [
    # Authentication endpoints
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    
    # Profile endpoint
    path('profile/', views.UserProfileView.as_view(), name='profile'),
    
    # Marketplace items endpoints
    path('items/', views.ItemListCreateView.as_view(), name='item-list-create'),
    
    # Negotiation endpoints
    path('negotiations/', views.NegotiationListView.as_view(), name='negotiation-list'),
    path('negotiations/initiate/', views.NegotiationInitiateView.as_view(), name='negotiation-initiate'),
    path('negotiations/<int:pk>/', views.NegotiationDetailView.as_view(), name='negotiation-detail'),
    path('negotiations/<int:pk>/step/', views.NegotiationStepView.as_view(), name='negotiation-step'),
]

