# api/serializers.py

from rest_framework import serializers
from .models import EmailAccount, Email, ExtractedReservation, SyncLog, Transaction


class EmailAccountSerializer(serializers.ModelSerializer):
    """Serializer pour les comptes email"""
    
    class Meta:
        model = EmailAccount
        fields = ['id', 'email_address', 'auth_type', 'imap_server', 'imap_port', 'is_active', 'last_sync', 'created_at']
        read_only_fields = ['id', 'last_sync', 'created_at']
    
    # Ne jamais exposer le mot de passe dans l'API
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Le mot de passe n'est jamais retourné
        return data


class EmailAccountCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer un compte email (avec mot de passe)"""
    
    class Meta:
        model = EmailAccount
        fields = ['email_address', 'password', 'imap_server', 'imap_port', 'is_active']
    
    def create(self, validated_data):
        # Associe automatiquement au user authentifié
        validated_data['user'] = self.context['request'].user
        validated_data['auth_type'] = 'imap'
        return super().create(validated_data)


class EmailSerializer(serializers.ModelSerializer):
    """Serializer pour les emails"""
    
    class Meta:
        model = Email
        fields = ['id', 'subject', 'sender', 'recipient', 'date', 'is_read', 'is_processed', 'received_at']
        read_only_fields = ['id', 'received_at']


class EmailDetailSerializer(serializers.ModelSerializer):
    """Serializer détaillé pour un email (avec body)"""
    
    class Meta:
        model = Email
        fields = ['id', 'subject', 'sender', 'recipient', 'date', 'body_text', 'body_html', 
                  'is_read', 'is_processed', 'received_at']
        read_only_fields = ['id', 'received_at']


class ExtractedReservationSerializer(serializers.ModelSerializer):
    """Serializer pour les réservations extraites"""
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = ExtractedReservation
        fields = [
            'id', 'platform', 'platform_display', 'service_type', 'service_type_display',
            'status', 'status_display', 'reservation_number',
            'client_name', 'client_email', 'client_phone',
            'start_date', 'start_time', 'end_date', 'end_time',
            'price', 'currency', 'extracted_data', 'is_upcoming',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ReservationStatsSerializer(serializers.Serializer):
    """Serializer pour les statistiques"""
    total_reservations = serializers.IntegerField()
    upcoming_reservations = serializers.IntegerField()
    completed_reservations = serializers.IntegerField()
    total_spent = serializers.DecimalField(max_digits=10, decimal_places=2)
    by_platform = serializers.DictField()
    by_month = serializers.DictField()


class SyncLogSerializer(serializers.ModelSerializer):
    """Serializer pour les logs de synchronisation"""
    account_email = serializers.CharField(source='account.email_address', read_only=True)
    
    class Meta:
        model = SyncLog
        fields = ['id', 'account_email', 'sync_date', 'emails_fetched', 
                  'reservations_extracted', 'status', 'error_message', 'duration']
        read_only_fields = ['id', 'sync_date']


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer pour les transactions"""
    
    class Meta:
        model = Transaction
        fields = ['id', 'text', 'ammount', 'created_at']
        read_only_fields = ['id', 'created_at']