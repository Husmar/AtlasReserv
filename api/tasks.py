# api/tasks.py

from celery import shared_task
import imaplib
import email
from email.header import decode_header
from django.utils import timezone
from .models import EmailAccount, Email, ExtractedReservation, SyncLog
from .extractors import GenericParkingExtractor


@shared_task
def sync_all_emails():
    """Synchronise tous les comptes email actifs"""
    active_accounts = EmailAccount.objects.filter(is_active=True)
    
    for account in active_accounts:
        sync_single_account.delay(account.id)


@shared_task
def sync_single_account(account_id):
    """Synchronise un seul compte email"""
    try:
        account = EmailAccount.objects.get(id=account_id)
        start_time = timezone.now()
        
        # Connexion IMAP
        mail = imaplib.IMAP4_SSL(account.imap_server, account.imap_port)
        mail.login(account.email_address, account.password)
        mail.select('inbox')
        
        # Recherche des emails non lus
        status, messages = mail.search(None, 'UNSEEN')
        
        emails_fetched = 0
        
        for num in messages[0].split():
            status, msg_data = mail.fetch(num, '(RFC822)')
            
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Extraction des données
                    subject = decode_header(msg['Subject'])[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode()
                    
                    sender = msg['From']
                    message_id = msg['Message-ID']
                    
                    # Corps HTML
                    body_html = ''
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/html":
                                body_html = part.get_payload(decode=True).decode()
                                break
                    else:
                        if msg.get_content_type() == "text/html":
                            body_html = msg.get_payload(decode=True).decode()
                    
                    # Sauvegarde en BDD
                    email_obj, created = Email.objects.get_or_create(
                        message_id=message_id,
                        defaults={
                            'account': account,
                            'subject': subject,
                            'sender': sender,
                            'recipient': account.email_address,
                            'date': timezone.now(),
                            'body_html': body_html,
                        }
                    )
                    
                    if created:
                        emails_fetched += 1
        
        mail.close()
        mail.logout()
        
        # Mise à jour
        account.last_sync = timezone.now()
        account.save()
        
        # Log
        duration = (timezone.now() - start_time).total_seconds()
        SyncLog.objects.create(
            account=account,
            emails_fetched=emails_fetched,
            status='success',
            duration=duration
        )
        
        # Lancer l'extraction
        process_parking_emails.delay()
        
        return f"{emails_fetched} emails récupérés"
        
    except Exception as e:
        SyncLog.objects.create(
            account=account,
            status='error',
            error_message=str(e)
        )
        return f"Erreur: {str(e)}"


@shared_task
def process_parking_emails():
    """
    Traite tous les emails de parking non traités
    avec l'extracteur générique
    """
    extractor = GenericParkingExtractor()
    
    # Récupère les emails non traités
    unprocessed = Email.objects.filter(is_processed=False)
    
    reservations_created = 0
    
    for email_obj in unprocessed:
        # Vérifie si c'est un email de parking
        if not extractor.can_handle(email_obj):
            continue
        
        try:
            # Extraction
            data = extractor.extract(email_obj)
            
            if data.get('reservation_number'):
                # Création de la réservation
                reservation, created = ExtractedReservation.objects.update_or_create(
                    platform=data['platform'],
                    reservation_number=data['reservation_number'],
                    defaults={
                        'email': email_obj,
                        'service_type': 'parking',
                        'client_name': data.get('client_name', ''),
                        'client_phone': data.get('client_phone', ''),
                        'client_email': data.get('client_email', ''),
                        'start_date': data.get('start_date'),
                        'start_time': data.get('start_time'),
                        'end_date': data.get('end_date'),
                        'end_time': data.get('end_time'),
                        'price': data.get('price'),
                        'currency': data.get('currency', 'EUR'),
                        'extracted_data': data.get('extracted_data', {}),
                    }
                )
                
                if created:
                    reservations_created += 1
                
                # Marquer comme traité
                email_obj.is_processed = True
                email_obj.save()
        
        except Exception as e:
            print(f"Erreur extraction email {email_obj.id}: {e}")
            continue
    
    return f"{reservations_created} réservations créées"