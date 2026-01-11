# parking_app/models.py

from django.db import models
from django.contrib.auth.models import User
from encrypted_model_fields.fields import EncryptedCharField, EncryptedTextField


class EmailAccount(models.Model):
    """Compte email d'un client"""
    
    AUTH_TYPE_CHOICES = [
        ('imap', 'IMAP (mot de passe)'),
        ('oauth_google', 'Google OAuth'),
        ('oauth_microsoft', 'Microsoft OAuth'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_accounts')
    email_address = models.EmailField(unique=True)
    auth_type = models.CharField(max_length=20, choices=AUTH_TYPE_CHOICES, default='imap')
    
    # Pour IMAP classique
    password = EncryptedCharField(max_length=255, blank=True, null=True)
    imap_server = models.CharField(max_length=255, default='imap.gmail.com', blank=True)
    imap_port = models.IntegerField(default=993)
    
    # Pour OAuth
    oauth_tokens = EncryptedTextField(blank=True, null=True)  # JSON avec access_token, refresh_token, etc.
    
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Compte Email"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.email_address} ({self.user.username})"
    
    def get_oauth_tokens(self) -> dict:
        """Retourne les tokens OAuth parsés"""
        import json
        if self.oauth_tokens:
            return json.loads(self.oauth_tokens)
        return {}
    
    def set_oauth_tokens(self, tokens: dict):
        """Stocke les tokens OAuth"""
        import json
        self.oauth_tokens = json.dumps(tokens)


class Email(models.Model):
    """Email brut reçu"""
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, related_name='emails')
    message_id = models.CharField(max_length=255, unique=True, db_index=True)
    subject = models.CharField(max_length=500)
    sender = models.CharField(max_length=255, db_index=True)
    recipient = models.CharField(max_length=255)
    date = models.DateTimeField(db_index=True)
    body_text = models.TextField(blank=True)
    body_html = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    is_processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Email"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['account', '-date']),
            models.Index(fields=['sender', '-date']),
        ]
    
    def __str__(self):
        return f"{self.subject} - {self.sender}"


class ExtractedReservation(models.Model):
    """Réservation extraite (tous types)"""
    
    PLATFORM_CHOICES = [
        ('parkos', 'Parkos'),
        ('parkmundo', 'ParkMundo'),
        ('travelcar', 'TravelCar'),
        ('ector', 'Ector'),
        ('onepark', 'OnePark'),
        ('other', 'Autre'),
    ]
    
    SERVICE_TYPE_CHOICES = [
        ('parking', 'Parking'),
        ('hotel', 'Hôtel'),
        ('car_rental', 'Location voiture'),
        ('flight', 'Vol'),
        ('other', 'Autre'),
    ]
    
    STATUS_CHOICES = [
        ('confirmed', 'Confirmée'),
        ('pending', 'En attente'),
        ('cancelled', 'Annulée'),
        ('completed', 'Terminée'),
    ]
    
    email = models.ForeignKey(Email, on_delete=models.CASCADE, related_name='reservations')
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES, db_index=True)
    service_type = models.CharField(max_length=50, choices=SERVICE_TYPE_CHOICES, db_index=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='confirmed')
    reservation_number = models.CharField(max_length=100, db_index=True)
    
    # Infos client
    client_name = models.CharField(max_length=255, blank=True)
    client_email = models.EmailField(blank=True)
    client_phone = models.CharField(max_length=50, blank=True)
    
    # Dates
    start_date = models.DateField(null=True, blank=True, db_index=True)
    start_time = models.TimeField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    end_time = models.TimeField(null=True, blank=True)
    
    # Prix
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='EUR')
    
    # Données spécifiques (JSON)
    extracted_data = models.JSONField(default=dict)
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Réservation Extraite"
        ordering = ['-start_date']
        unique_together = [['platform', 'reservation_number']]
    
    def __str__(self):
        return f"{self.get_platform_display()} #{self.reservation_number} - {self.client_name}"


class SyncLog(models.Model):
    """Log des synchronisations"""
    STATUS_CHOICES = [
        ('success', 'Succès'),
        ('error', 'Erreur'),
        ('partial', 'Partiel'),
    ]
    
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, related_name='sync_logs')
    sync_date = models.DateTimeField(auto_now_add=True)
    emails_fetched = models.IntegerField(default=0)
    reservations_extracted = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True)
    duration = models.FloatField(null=True)
    
    class Meta:
        verbose_name = "Log de Synchronisation"
        ordering = ['-sync_date']
    
    def __str__(self):
        return f"{self.account.email_address} - {self.sync_date} ({self.status})"


class Transaction(models.Model):
    """Transaction financière"""
    text = models.CharField(max_length=255)
    ammount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Transaction"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.text} - {self.ammount}€"