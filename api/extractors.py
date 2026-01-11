# api/extractors.py

import re
from datetime import datetime
from bs4 import BeautifulSoup


class GenericParkingExtractor:
    """
    Extracteur générique pour les emails de réservation de parking.
    Supporte Parkos, ParkMundo, TravelCar, Ector, OnePark, etc.
    """
    
    PLATFORM_PATTERNS = {
        'parkos': ['parkos', 'parkos.com', 'parkos.fr'],
        'parkmundo': ['parkmundo', 'parkmundo.com'],
        'travelcar': ['travelcar', 'travel-car'],
        'ector': ['ector', 'ector-parking'],
        'onepark': ['onepark', 'one-park'],
    }
    
    def can_handle(self, email_obj):
        """Vérifie si cet extracteur peut traiter l'email"""
        sender = email_obj.sender.lower()
        subject = email_obj.subject.lower()
        
        keywords = ['réservation', 'reservation', 'booking', 'confirmation', 
                    'parking', 'stationnement']
        
        for keyword in keywords:
            if keyword in sender or keyword in subject:
                return True
        
        for platform, patterns in self.PLATFORM_PATTERNS.items():
            for pattern in patterns:
                if pattern in sender or pattern in subject:
                    return True
        
        return False
    
    def detect_platform(self, email_obj):
        """Détecte la plateforme de réservation"""
        sender = email_obj.sender.lower()
        subject = email_obj.subject.lower()
        body = email_obj.body_html.lower() if email_obj.body_html else ''
        
        content = f"{sender} {subject} {body}"
        
        for platform, patterns in self.PLATFORM_PATTERNS.items():
            for pattern in patterns:
                if pattern in content:
                    return platform
        
        return 'other'
    
    def extract(self, email_obj):
        """Extrait les données de réservation de l'email"""
        data = {
            'platform': self.detect_platform(email_obj),
            'reservation_number': None,
            'client_name': None,
            'client_email': None,
            'client_phone': None,
            'start_date': None,
            'start_time': None,
            'end_date': None,
            'end_time': None,
            'price': None,
            'currency': 'EUR',
            'extracted_data': {},
        }
        
        # Parse le HTML
        html = email_obj.body_html or ''
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ')
        
        # Extraction du numéro de réservation
        data['reservation_number'] = self._extract_reservation_number(text)
        
        # Extraction des dates
        dates = self._extract_dates(text)
        if dates:
            data['start_date'] = dates.get('start_date')
            data['start_time'] = dates.get('start_time')
            data['end_date'] = dates.get('end_date')
            data['end_time'] = dates.get('end_time')
        
        # Extraction du prix
        data['price'] = self._extract_price(text)
        
        # Extraction du nom client
        data['client_name'] = self._extract_client_name(text)
        
        # Extraction du téléphone
        data['client_phone'] = self._extract_phone(text)
        
        # Données brutes
        data['extracted_data'] = {
            'raw_text': text[:2000],
            'sender': email_obj.sender,
            'subject': email_obj.subject,
        }
        
        return data
    
    def _extract_reservation_number(self, text):
        """Extrait le numéro de réservation"""
        patterns = [
            r'[Rr]éservation\s*(?:#|n°|numero|number)?\s*[:.]?\s*([A-Z0-9-]{5,20})',
            r'[Bb]ooking\s*(?:#|n°|numero|number)?\s*[:.]?\s*([A-Z0-9-]{5,20})',
            r'[Cc]onfirmation\s*(?:#|n°|numero|number)?\s*[:.]?\s*([A-Z0-9-]{5,20})',
            r'(?:N°|#|Ref)\s*[:.]?\s*([A-Z0-9-]{5,20})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_dates(self, text):
        """Extrait les dates d'arrivée et de départ"""
        result = {}
        
        # Pattern pour les dates (DD/MM/YYYY, DD-MM-YYYY, etc.)
        date_pattern = r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
        time_pattern = r'(\d{1,2}[hH:]\d{2})'
        
        dates_found = re.findall(date_pattern, text)
        times_found = re.findall(time_pattern, text)
        
        if len(dates_found) >= 2:
            try:
                result['start_date'] = self._parse_date(dates_found[0])
                result['end_date'] = self._parse_date(dates_found[1])
            except Exception:
                pass
        elif len(dates_found) == 1:
            try:
                result['start_date'] = self._parse_date(dates_found[0])
            except Exception:
                pass
        
        if len(times_found) >= 2:
            result['start_time'] = self._parse_time(times_found[0])
            result['end_time'] = self._parse_time(times_found[1])
        elif len(times_found) == 1:
            result['start_time'] = self._parse_time(times_found[0])
        
        return result
    
    def _parse_date(self, date_str):
        """Parse une chaîne de date"""
        date_str = date_str.replace('-', '/').strip()
        
        formats = ['%d/%m/%Y', '%d/%m/%y', '%Y/%m/%d']
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    def _parse_time(self, time_str):
        """Parse une chaîne d'heure"""
        time_str = time_str.replace('h', ':').replace('H', ':').strip()
        
        try:
            return datetime.strptime(time_str, '%H:%M').time()
        except ValueError:
            return None
    
    def _extract_price(self, text):
        """Extrait le prix"""
        patterns = [
            r'(\d+[.,]\d{2})\s*€',
            r'€\s*(\d+[.,]\d{2})',
            r'[Pp]rix\s*[:.]?\s*(\d+[.,]\d{2})',
            r'[Tt]otal\s*[:.]?\s*(\d+[.,]\d{2})',
            r'[Mm]ontant\s*[:.]?\s*(\d+[.,]\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                price_str = match.group(1).replace(',', '.')
                try:
                    return float(price_str)
                except ValueError:
                    continue
        
        return None
    
    def _extract_client_name(self, text):
        """Extrait le nom du client"""
        patterns = [
            r'[Nn]om\s*[:.]?\s*([A-ZÀ-Ÿ][a-zà-ÿ]+\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)',
            r'[Cc]lient\s*[:.]?\s*([A-ZÀ-Ÿ][a-zà-ÿ]+\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)',
            r'[Bb]onjour\s+([A-ZÀ-Ÿ][a-zà-ÿ]+)',
            r'[Cc]her\s+([A-ZÀ-Ÿ][a-zà-ÿ]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_phone(self, text):
        """Extrait le numéro de téléphone"""
        patterns = [
            r'(?:\+33|0)\s*[1-9](?:[\s.-]*\d{2}){4}',
            r'[Tt]él(?:éphone)?\s*[:.]?\s*([\d\s.-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                phone = match.group(0) if '(' not in pattern else match.group(1)
                return re.sub(r'[\s.-]', '', phone)
        
        return None
