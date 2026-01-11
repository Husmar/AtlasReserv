# api/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes as perm_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.views import APIView
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.shortcuts import redirect
from django.conf import settings
from datetime import datetime, timedelta
from .models import EmailAccount, Email, ExtractedReservation, SyncLog, Transaction
from .serializers import (
    EmailAccountSerializer, EmailAccountCreateSerializer,
    EmailSerializer, EmailDetailSerializer,
    ExtractedReservationSerializer, ReservationStatsSerializer,
    SyncLogSerializer, TransactionSerializer
)
from .tasks import sync_single_account
from . import google_oauth


class GoogleOAuthInitView(APIView):
    """Initie le flow OAuth Google"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        redirect_uri = request.build_absolute_uri('/api/auth/google/callback/')
        # Le user_id est encodé dans le state, pas besoin de session
        authorization_url, state = google_oauth.get_authorization_url(redirect_uri, request.user.id)
        
        return Response({
            'authorization_url': authorization_url,
            'state': state
        })


class GoogleOAuthCallbackView(APIView):
    """Callback OAuth Google"""
    permission_classes = [AllowAny]  # Le callback vient de Google
    
    def get(self, request):
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        
        # URL de redirection frontend
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        
        if error:
            return redirect(f'{frontend_url}?oauth_error={error}')
        
        if not code:
            return redirect(f'{frontend_url}?oauth_error=no_code')
        
        # Décoder le user_id depuis le state (pas de session)
        state_data = google_oauth.decode_state(state)
        user_id = state_data.get('user_id')
        
        if not user_id:
            return redirect(f'{frontend_url}?oauth_error=invalid_state')
        
        try:
            redirect_uri = request.build_absolute_uri('/api/auth/google/callback/')
            tokens = google_oauth.exchange_code_for_tokens(code, redirect_uri)
            
            # Récupérer l'email de l'utilisateur Google
            email_address = google_oauth.get_user_email(tokens)
            
            from django.contrib.auth.models import User
            user = User.objects.get(id=user_id)
            
            # Créer ou mettre à jour le compte email
            account, created = EmailAccount.objects.update_or_create(
                email_address=email_address,
                defaults={
                    'user': user,
                    'auth_type': 'oauth_google',
                    'is_active': True,
                }
            )
            account.set_oauth_tokens(tokens)
            account.save()
            
            return redirect(f'{frontend_url}?oauth_success=true&email={email_address}')
            
        except Exception as e:
            return redirect(f'{frontend_url}?oauth_error={str(e)}')


class EmailAccountViewSet(viewsets.ModelViewSet):
    """
    API ViewSet pour les comptes email
    
    GET /api/email-accounts/ - Liste des comptes
    POST /api/email-accounts/ - Ajouter un compte
    GET /api/email-accounts/{id}/ - Détails d'un compte
    PUT /api/email-accounts/{id}/ - Modifier un compte
    DELETE /api/email-accounts/{id}/ - Supprimer un compte
    POST /api/email-accounts/{id}/sync/ - Forcer une synchro
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Chaque user voit seulement ses comptes
        return EmailAccount.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return EmailAccountCreateSerializer
        return EmailAccountSerializer
    
    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """Force la synchronisation d'un compte email"""
        account = self.get_object()
        
        # Lancer la tâche Celery
        task = sync_single_account.delay(account.id)
        
        return Response({
            'message': 'Synchronisation lancée',
            'task_id': task.id
        })
    
    @action(detail=True, methods=['get'])
    def test_connection(self, request, pk=None):
        """Teste la connexion OAuth en récupérant les derniers emails"""
        account = self.get_object()
        
        if account.auth_type != 'oauth_google':
            return Response({
                'success': False,
                'error': 'Ce compte utilise IMAP, pas OAuth'
            }, status=400)
        
        try:
            tokens = account.get_oauth_tokens()
            if not tokens:
                return Response({
                    'success': False,
                    'error': 'Pas de tokens OAuth stockés'
                }, status=400)
            
            # Récupérer quelques emails récents
            service = google_oauth.get_gmail_service(tokens)
            
            # Juste lister les 5 derniers emails
            results = service.users().messages().list(
                userId='me',
                maxResults=5
            ).execute()
            
            messages = results.get('messages', [])
            
            # Récupérer les sujets des emails
            email_previews = []
            for msg in messages[:5]:
                msg_data = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['Subject', 'From', 'Date']
                ).execute()
                
                headers = {h['name']: h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
                email_previews.append({
                    'subject': headers.get('Subject', '(Sans sujet)'),
                    'from': headers.get('From', ''),
                    'date': headers.get('Date', '')
                })
            
            return Response({
                'success': True,
                'email_address': account.email_address,
                'total_emails_found': len(messages),
                'recent_emails': email_previews
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class EmailViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API ViewSet pour les emails (lecture seule)
    
    GET /api/emails/ - Liste des emails
    GET /api/emails/{id}/ - Détails d'un email
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Emails des comptes du user
        return Email.objects.filter(account__user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return EmailDetailSerializer
        return EmailSerializer
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Marquer un email comme lu"""
        email = self.get_object()
        email.is_read = True
        email.save()
        return Response({'status': 'marked as read'})


class ReservationViewSet(viewsets.ModelViewSet):
    """
    API ViewSet pour les réservations
    
    GET /api/reservations/ - Liste des réservations
    GET /api/reservations/{id}/ - Détails d'une réservation
    PUT /api/reservations/{id}/ - Modifier une réservation
    DELETE /api/reservations/{id}/ - Supprimer une réservation
    GET /api/reservations/upcoming/ - Réservations à venir
    GET /api/reservations/stats/ - Statistiques
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ExtractedReservationSerializer
    
    def get_queryset(self):
        # Réservations des comptes du user
        queryset = ExtractedReservation.objects.filter(
            email__account__user=self.request.user
        )
        
        # Filtres optionnels
        platform = self.request.query_params.get('platform')
        service_type = self.request.query_params.get('service_type')
        status_filter = self.request.query_params.get('status')
        
        if platform:
            queryset = queryset.filter(platform=platform)
        if service_type:
            queryset = queryset.filter(service_type=service_type)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Récupère les réservations à venir"""
        today = timezone.now().date()
        
        reservations = self.get_queryset().filter(
            start_date__gte=today
        ).order_by('start_date')
        
        serializer = self.get_serializer(reservations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def past(self, request):
        """Récupère les réservations passées"""
        today = timezone.now().date()
        
        reservations = self.get_queryset().filter(
            end_date__lt=today
        ).order_by('-end_date')
        
        serializer = self.get_serializer(reservations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Statistiques des réservations"""
        queryset = self.get_queryset()
        today = timezone.now().date()
        
        # Stats globales
        total = queryset.count()
        upcoming = queryset.filter(start_date__gte=today).count()
        completed = queryset.filter(end_date__lt=today).count()
        total_spent = queryset.aggregate(total=Sum('price'))['total'] or 0
        
        # Par plateforme
        by_platform = dict(
            queryset.values('platform').annotate(count=Count('id')).values_list('platform', 'count')
        )
        
        # Par mois (6 derniers mois)
        six_months_ago = today - timedelta(days=180)
        by_month = {}
        for i in range(6):
            month_start = six_months_ago + timedelta(days=30*i)
            month_end = month_start + timedelta(days=30)
            count = queryset.filter(
                start_date__gte=month_start,
                start_date__lt=month_end
            ).count()
            by_month[month_start.strftime('%Y-%m')] = count
        
        data = {
            'total_reservations': total,
            'upcoming_reservations': upcoming,
            'completed_reservations': completed,
            'total_spent': total_spent,
            'by_platform': by_platform,
            'by_month': by_month,
        }
        
        serializer = ReservationStatsSerializer(data)
        return Response(serializer.data)


class SyncLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API ViewSet pour les logs de synchronisation
    
    GET /api/sync-logs/ - Liste des logs
    GET /api/sync-logs/{id}/ - Détails d'un log
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SyncLogSerializer
    
    def get_queryset(self):
        return SyncLog.objects.filter(
            account__user=self.request.user
        ).order_by('-sync_date')


class TransactionListCreate(ListCreateAPIView):
    """
    API pour lister et créer des transactions
    
    GET /api/transactions/ - Liste des transactions
    POST /api/transactions/ - Créer une transaction
    """
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Optionnel: filtrer par user si Transaction a un champ user
        return Transaction.objects.all().order_by('-created_at')


class TransactionDetail(RetrieveUpdateDestroyAPIView):
    """
    API pour afficher, modifier et supprimer une transaction
    
    GET /api/transactions/{id}/ - Détails d'une transaction
    PUT /api/transactions/{id}/ - Modifier une transaction
    PATCH /api/transactions/{id}/ - Modification partielle
    DELETE /api/transactions/{id}/ - Supprimer une transaction
    """
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'pk'