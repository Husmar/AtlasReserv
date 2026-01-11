# api/google_oauth.py

import os
import json
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from django.conf import settings

# Scopes nécessaires pour lire les emails
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

def get_google_flow(redirect_uri: str) -> Flow:
    """Crée un flow OAuth2 pour Google"""
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    
    return flow


def encode_state(user_id: int) -> str:
    """Encode le user_id dans le state parameter"""
    data = json.dumps({'user_id': user_id})
    return base64.urlsafe_b64encode(data.encode()).decode()


def decode_state(state: str) -> dict:
    """Decode le state parameter"""
    try:
        data = base64.urlsafe_b64decode(state.encode()).decode()
        return json.loads(data)
    except Exception:
        return {}


def get_authorization_url(redirect_uri: str, user_id: int) -> tuple[str, str]:
    """Génère l'URL d'autorisation Google"""
    flow = get_google_flow(redirect_uri)
    
    # Encoder le user_id dans le state
    state = encode_state(user_id)
    
    authorization_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=state
    )
    
    return authorization_url, state


def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    """Échange le code d'autorisation contre des tokens"""
    flow = get_google_flow(redirect_uri)
    flow.fetch_token(code=code)
    
    credentials = flow.credentials
    
    return {
        'access_token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': list(credentials.scopes),
        'expiry': credentials.expiry.isoformat() if credentials.expiry else None,
    }


def get_gmail_service(credentials_data: dict):
    """Crée un service Gmail à partir des credentials stockés"""
    credentials = Credentials(
        token=credentials_data.get('access_token'),
        refresh_token=credentials_data.get('refresh_token'),
        token_uri=credentials_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=credentials_data.get('client_id', settings.GOOGLE_CLIENT_ID),
        client_secret=credentials_data.get('client_secret', settings.GOOGLE_CLIENT_SECRET),
        scopes=credentials_data.get('scopes', SCOPES),
    )
    
    return build('gmail', 'v1', credentials=credentials)


def get_user_email(credentials_data: dict) -> str:
    """Récupère l'adresse email de l'utilisateur"""
    service = get_gmail_service(credentials_data)
    profile = service.users().getProfile(userId='me').execute()
    return profile.get('emailAddress', '')


def fetch_emails_oauth(credentials_data: dict, max_results: int = 50) -> list:
    """Récupère les emails via l'API Gmail"""
    service = get_gmail_service(credentials_data)
    
    # Recherche des emails de réservation
    query = 'subject:(réservation OR reservation OR booking OR confirmation) newer_than:30d'
    
    results = service.users().messages().list(
        userId='me',
        q=query,
        maxResults=max_results
    ).execute()
    
    messages = results.get('messages', [])
    emails = []
    
    for msg in messages:
        # Récupérer le contenu complet
        message = service.users().messages().get(
            userId='me',
            id=msg['id'],
            format='full'
        ).execute()
        
        headers = message.get('payload', {}).get('headers', [])
        
        email_data = {
            'message_id': message.get('id'),
            'thread_id': message.get('threadId'),
            'subject': next((h['value'] for h in headers if h['name'].lower() == 'subject'), ''),
            'sender': next((h['value'] for h in headers if h['name'].lower() == 'from'), ''),
            'date': next((h['value'] for h in headers if h['name'].lower() == 'date'), ''),
            'body_html': _get_email_body(message),
        }
        
        emails.append(email_data)
    
    return emails


def _get_email_body(message: dict) -> str:
    """Extrait le corps HTML de l'email"""
    import base64
    
    payload = message.get('payload', {})
    
    # Email simple
    if 'body' in payload and payload['body'].get('data'):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    
    # Email multipart
    parts = payload.get('parts', [])
    for part in parts:
        if part.get('mimeType') == 'text/html':
            data = part.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        
        # Nested parts
        if 'parts' in part:
            for subpart in part['parts']:
                if subpart.get('mimeType') == 'text/html':
                    data = subpart.get('body', {}).get('data', '')
                    if data:
                        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    
    # Fallback to text/plain
    for part in parts:
        if part.get('mimeType') == 'text/plain':
            data = part.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    
    return ''
