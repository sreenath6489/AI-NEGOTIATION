import requests
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework import status, views, permissions, generics
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from .models import UserProfile, Item, Negotiation, NegotiationMessage
from .serializers import (
    UserSerializer, UserProfileSerializer, ItemSerializer,
    NegotiationSerializer, NegotiationMessageSerializer
)
from .services.gemini_negotiator import step_negotiation_session

# --- AUTHENTICATION VIEWS ---

class RegisterView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        email = request.data.get('email', '')

        if not username or not password:
            return Response(
                {"error": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(username=username).exists():
            return Response(
                {"error": "Username already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create user
        user = User.objects.create_user(username=username, password=password, email=email)
        # Create empty profile
        UserProfile.objects.create(user=user)
        # Create token
        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            "token": token.key,
            "user": UserSerializer(user).data,
            "profile_complete": False
        }, status=status.HTTP_201_CREATED)

class LoginView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response(
                {"error": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(username=username, password=password)
        if not user:
            return Response(
                {"error": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        profile_complete = False
        if hasattr(user, 'profile'):
            profile_complete = bool(user.profile.location and user.profile.phone_number)

        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "token": token.key,
            "user": UserSerializer(user).data,
            "profile_complete": profile_complete
        })

class GoogleLoginView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        credential = request.data.get('credential')
        if not credential:
            return Response(
                {"error": "Google credential token is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Verify the JWT credential token by contacting Google's validation API
            verify_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}"
            response = requests.get(verify_url, timeout=10)
            if response.status_code != 200:
                return Response(
                    {"error": "Invalid Google credential token."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            token_info = response.json()
            email = token_info.get('email')
            if not email:
                return Response(
                    {"error": "Email not provided by Google account."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            first_name = token_info.get('given_name', '')
            last_name = token_info.get('family_name', '')

            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                # Create user with safe unique username derived from email
                username = email.split('@')[0]
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1

                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name
                )
                # Create empty profile
                UserProfile.objects.create(user=user)

            profile_complete = False
            if hasattr(user, 'profile'):
                profile_complete = bool(user.profile.location and user.profile.phone_number)

            token, _ = Token.objects.get_or_create(user=user)
            return Response({
                "token": token.key,
                "user": UserSerializer(user).data,
                "profile_complete": profile_complete
            })
        except Exception as e:
            return Response(
                {"error": f"Google verification failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ConfigView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        import os
        return Response({
            "google_client_id": os.getenv('GOOGLE_CLIENT_ID', 'YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com')
        })

# --- USER PROFILE VIEW ---

class UserProfileView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        serializer = UserProfileSerializer(profile)
        return Response(serializer.data)

    def post(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(UserSerializer(request.user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# --- MARKETPLACE LISTINGS VIEWS ---

class ItemListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    queryset = Item.objects.filter(status='active').order_by('-created_at')
    serializer_class = ItemSerializer

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user)

# --- NEGOTIATION VIEWS ---

class NegotiationInitiateView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        item_id = request.data.get('item_id')
        buyer_max_budget = request.data.get('buyer_max_budget')
        buyer_strategy = request.data.get('buyer_strategy', 'diplomat')

        if not item_id or not buyer_max_budget:
            return Response(
                {"error": "item_id and buyer_max_budget are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist:
            return Response({"error": "Item not found."}, status=status.HTTP_404_NOT_FOUND)

        if item.seller == request.user:
            return Response(
                {"error": "You cannot negotiate on your own listing."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create or fetch active negotiation session for this buyer on this item
        negotiation, created = Negotiation.objects.get_or_create(
            item=item,
            buyer=request.user,
            defaults={
                'buyer_max_budget': buyer_max_budget,
                'buyer_strategy': buyer_strategy,
                'status': 'negotiating'
            }
        )
        
        # If it already existed but was closed, we can reset it
        if not created and negotiation.status != 'negotiating':
            negotiation.status = 'negotiating'
            negotiation.buyer_max_budget = buyer_max_budget
            negotiation.buyer_strategy = buyer_strategy
            negotiation.agreed_price = None
            negotiation.save()
            # Clear old messages to start fresh
            negotiation.messages.all().delete()

        # Add initial system message
        NegotiationMessage.objects.create(
            negotiation=negotiation,
            sender='system',
            content=f"Negotiation started. Buyer's AI Agent ({negotiation.buyer_strategy}) vs Seller's AI Agent ({item.seller_strategy}).",
            price_offered=None
        )

        return Response(NegotiationSerializer(negotiation).data, status=status.HTTP_201_CREATED)

class NegotiationStepView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            negotiation = Negotiation.objects.get(id=pk)
        except Negotiation.DoesNotExist:
            return Response({"error": "Negotiation session not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check if user is either buyer or seller
        if negotiation.buyer != request.user and negotiation.item.seller != request.user:
            return Response(
                {"error": "You do not have access to this negotiation session."},
                status=status.HTTP_403_FORBIDDEN
            )

        if negotiation.status != 'negotiating':
            return Response(
                {"error": f"Negotiation has already concluded with status '{negotiation.status}'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            step_negotiation_session(negotiation)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(NegotiationSerializer(negotiation).data)

class NegotiationListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NegotiationSerializer

    def get_queryset(self):
        # Return negotiations where user is either buyer or seller
        user = self.request.user
        return Negotiation.objects.filter(
            buyer=user
        ) | Negotiation.objects.filter(
            item__seller=user
        )

class NegotiationDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NegotiationSerializer

    def get_queryset(self):
        user = self.request.user
        return Negotiation.objects.filter(buyer=user) | Negotiation.objects.filter(item__seller=user)

