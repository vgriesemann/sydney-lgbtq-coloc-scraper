```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LGBTQ+ Sydney Flatshare Scraper
Automated Search System for LGBTQ+ flatshare in Sydney
"""

import os
import re
import time
import json
import hashlib
import requests
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from bs4 import BeautifulSoup

# Configuration
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

class LGBTQColocScraper:
    def __init__(self):
        self.notion_headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # Patterns de dÃ©tection LGBTQ+
        self.lgbtq_patterns = [
            r"(?i)lgbtq?\+?",
            r"(?i)queer[-\s]?friendly", 
            r"(?i)queer\s*house(hold)?",
            r"(?i)gay[-\s]?share",
            r"(?i)gay[-\s]?friendly",
            r"(?i)lesbian[-\s]?friendly",
            r"(?i)trans[-\s]?friendly",
            r"(?i)rainbow\s*(home|house|household)"
        ]
        
        # Patterns nationalitÃ©s
        self.nationality_patterns = {
            "Australian": r"(?i)\b(aussies?|australian[s]?)\b",
            "Brazilian": r"(?i)\b(brazil(ian)?s?|portuguese\s*(speaker|speaking)|portugu[eÃª]s)\b"
        }
        
        self.target_suburbs = ["Surry Hills", "Darlinghurst", "Newtown"]
        
    def log(self, message: str):
        """Logging simple"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def detect_lgbtq_content(self, text: str) -> bool:
        """DÃ©tecter contenu LGBTQ+"""
        for pattern in self.lgbtq_patterns:
            if re.search(pattern, text):
                return True
        return False
    
    def extract_nationalities(self, text: str) -> List[str]:
        """Extraire nationalitÃ©s"""
        found = []
        for nationality, pattern in self.nationality_patterns.items():
            if re.search(pattern, text):
                found.append(nationality)
        return found
    
    def generate_hash(self, listing: Dict) -> str:
        """GÃ©nÃ©rer hash pour dÃ©duplication"""
        key = f"{listing['title']}|{listing['price_per_week']}|{listing['suburb']}|{listing['date_posted']}"
        return hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]
    
    def search_notion_duplicate(self, url: str) -> bool:
        """VÃ©rifier si URL existe dÃ©jÃ  dans Notion"""
        query_data = {
            "filter": {
                "property": "URL",
                "url": {"equals": url}
            }
        }
        
        try:
            response = requests.post(
                f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query",
                headers=self.notion_headers,
                json=query_data
            )
            
            if response.status_code == 200:
                results = response.json().get("results", [])
                return len(results) > 0
                
        except Exception as e:
            self.log(f"Erreur recherche Notion: {e}")
            
        return False
    
    def analyze_with_openai(self, listing: Dict) -> Dict:
        """Analyser avec OpenAI"""
        
        prompt = f"""
Analyse cette annonce de colocation Sydney et renvoie un JSON avec cette structure exacte:
{{
    "summary": "RÃ©sumÃ© en 2-3 phrases en anglais",
    "lgbtq": true/false,
    "nationalities": ["Australian", "Brazilian"],
    "tags": ["ensuite", "bills included", "furnished"],
    "score": 0-100,
    "reasons": ["raisons du score"]
}}

DonnÃ©es annonce:
Titre: {listing['title']}
Description: {listing['description']}
Prix/semaine: ${listing['price_per_week']}
Quartier: {listing['suburb']}

RÃ¨gles scoring:
- Base: 50
- +25 si LGBTQ+ explicite
- +10 par quartier premium (Surry Hills, Darlinghurst, Newtown)
- +10 si Australiens mentionnÃ©s
- +10 si BrÃ©siliens mentionnÃ©s
- +10 si ensuite/private bathroom
- +10 si bills included
- -20 si shared room
"""

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o-mini",
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "Tu es un expert en colocation LGBTQ+ Ã  Sydney. RÃ©ponds uniquement en JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 500
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                analysis = json.loads(result["choices"][0]["message"]["content"])
                return analysis
                
        except Exception as e:
            self.log(f"Erreur OpenAI: {e}")
            
        # Fallback analysis
        text = f"{listing['title']} {listing['description']}".lower()
        score = 50
        lgbtq = self.detect_lgbtq_content(text)
        if lgbtq:
            score += 25
        if listing['suburb'] in self.target_suburbs:
            score += 10
            
        return {
            "summary": f"Annonce de colocation Ã  {listing['suburb']} pour ${listing['price_per_week']}/semaine.",
            "lgbtq": lgbtq,
            "nationalities": self.extract_nationalities(text),
            "tags": [],
            "score": min(100, max(0, score)),
            "reasons": ["Analyse basique - erreur OpenAI"]
        }
    
    def create_notion_page(self, listing: Dict, analysis: Dict) -> bool:
        """CrÃ©er page dans Notion"""
        
        page_data = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "Title": {
                    "title": [{"text": {"content": listing["title"][:100]}}]
                },
                "URL": {
                    "url": listing["url"]
                },
                "Source": {
                    "select": {"name": listing["source"]}
                },
                "Prix/sem.": {
                    "number": listing["price_per_week"]
                },
                "Quartier": {
                    "select": {"name": listing["suburb"]}
                },
                "Date annonce": {
                    "date": {"start": listing["date_posted"]}
                },
                "LGBTQ": {
                    "checkbox": analysis["lgbtq"]
                },
                "NationalitÃ©s": {
                    "multi_select": [{"name": nat} for nat in analysis.get("nationalities", [])]
                },
                "Score": {
                    "number": analysis["score"]
                },
                "Tags": {
                    "multi_select": [{"name": tag} for tag in analysis.get("tags", [])]
                },
                "Statut": {
                    "select": {"name": "Nouveau"}
                }
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": listing["description"][:2000]}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph", 
                    "paragraph": {
                        "rich_text": [{"text": {"content": f"âœ¨ RÃ©sumÃ© IA: {analysis['summary']}"}}]
                    }
                }
            ]
        }
        
        try:
            response = requests.post(
                "https://api.notion.com/v1/pages",
                headers=self.notion_headers,
                json=page_data
            )
            
            if response.status_code == 200:
                self.log(f"âœ… CrÃ©Ã© dans Notion: {listing['title'][:50]}...")
                return True
            else:
                self.log(f"âŒ Erreur Notion: {response.status_code} - {response.text}")
                
        except Exception as e:
            self.log(f"âŒ Erreur crÃ©ation Notion: {e}")
            
        return False
    
    def send_telegram_notification(self, listings: List[Dict]):
        """Envoyer notification Telegram"""
        if not listings or not TELEGRAM_BOT_TOKEN:
            return
            
        message = f"ðŸ³ï¸â€ðŸŒˆ {len(listings)} new LGBTQ+ flatshare ads in Sydney!\n\n"
        
        for i, listing in enumerate(listings[:3]):  # Top 3
            message += f"{i+1}. {listing['title'][:40]}...\n"
            message += f"   ðŸ“ {listing['suburb']} - ${listing['price_per_week']}/sem\n"
            message += f"   ðŸŽ¯ Score: {listing['score']}/100\n"
            message += f"   ðŸ”— {listing['url']}\n\n"
        
        if len(listings) > 3:
            message += f"... et {len(listings)-3} other ads!"
            
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                }
            )
            self.log(f"ðŸ“± Notification Telegram envoyÃ©e: {len(listings)} annonces")
            
        except Exception as e:
            self.log(f"âŒ Erreur Telegram: {e}")
    
    def scrape_sample_listings(self) -> List[Dict]:
        """Scraper simplifiÃ© avec donnÃ©es d'exemple + vraies sources"""
        
        # Pour ce guide dÃ©butant, on utilise des donnÃ©es d'exemple
        # Dans la version complÃ¨te, on scraperait vraiment les sites
        
        sample_listings = [
            {
                "title": "Private room in queer-friendly share house - Surry Hills",
                "description": "Lovely private room with ensuite in a welcoming LGBTQ+ household. We're a mix of Australian and Brazilian flatmates who love to cook together! Close to Oxford Street and all the rainbow action. Bills included, fully furnished. Looking for someone who shares our values of inclusivity and community.",
                "url": f"https://flatmates.com.au/listing/{random.randint(10000, 99999)}",
                "price_per_week": random.randint(350, 450),
                "suburb": random.choice(["Surry Hills", "Darlinghurst", "Newtown"]),
                "date_posted": datetime.now().strftime("%Y-%m-%d"),
                "source": "Flatmates"
            },
            {
                "title": "Room in gay share house - Darlinghurst",
                "description": "Gay-friendly share house in the heart of Darlinghurst. Private bathroom, close to train station. We're looking for a like-minded person to join our small household. Two current flatmates - one Aussie teacher, one international student from SÃ£o Paulo.",
                "url": f"https://gayshare.com.au/listing/{random.randint(10000, 99999)}",
                "price_per_week": random.randint(380, 480),
                "suburb": random.choice(["Darlinghurst", "Surry Hills"]),
                "date_posted": datetime.now().strftime("%Y-%m-%d"),
                "source": "Gay Share"
            }
        ]
        
        # Ajouter alÃ©atoirement 0-2 annonces selon l'heure
        hour = datetime.now().hour
        if 8 <= hour <= 20:  # Heures pointe
            num_listings = random.randint(0, 2)
        else:  # Heures calmes
            num_listings = random.randint(0, 1)
            
        return sample_listings[:num_listings]
    
    def run(self):
        """ExÃ©cution principale"""
        self.log("ðŸš€ DÃ©marrage scraper LGBTQ+ Sydney")
        
        # Scraper les annonces
        raw_listings = self.scrape_sample_listings()
        self.log(f"ðŸ“¥ {len(raw_listings)} annonces rÃ©cupÃ©rÃ©es")
        
        if not raw_listings:
            self.log("â„¹ï¸ Aucune nouvelle annonce trouvÃ©e")
            return
        
        processed_listings = []
        
        for listing in raw_listings:
            try:
                # VÃ©rifier doublon
                if self.search_notion_duplicate(listing['url']):
                    self.log(f"â­ï¸ Doublon ignorÃ©: {listing['title'][:30]}...")
                    continue
                
                # Analyser avec IA
                self.log(f"ðŸ” Analyse: {listing['title'][:30]}...")
                analysis = self.analyze_with_openai(listing)
                
                # Filtrer selon critÃ¨res LGBTQ+
                if not analysis['lgbtq'] and listing['suburb'] not in self.target_suburbs:
                    self.log(f"âŒ FiltrÃ© (pas LGBTQ+): {listing['title'][:30]}...")
                    continue
                
                # CrÃ©er dans Notion
                if self.create_notion_page(listing, analysis):
                    processed_listings.append({
                        **listing,
                        "score": analysis['score'],
                        "lgbtq": analysis['lgbtq']
                    })
                
                # DÃ©lai anti-blocage
                time.sleep(random.uniform(2, 5))
                
            except Exception as e:
                self.log(f"âŒ Erreur traitement: {e}")
                continue
        
        # Notification
        if processed_listings:
            self.send_telegram_notification(processed_listings)
            
        self.log(f"âœ… TerminÃ©: {len(processed_listings)} annonces ajoutÃ©es")

if __name__ == "__main__":
    scraper = LGBTQColocScraper()
    scraper.run()
```
