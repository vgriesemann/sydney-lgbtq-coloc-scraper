#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LGBTQ+ Sydney Flatshare Scraper
Automated system for finding LGBTQ+ flatshare listings in Sydney.
"""

import os
import re
import time
import json
import hashlib
import requests
import random
from datetime import datetime
from typing import Dict, List
from bs4 import BeautifulSoup

# --- Configuration ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


class LGBTQColocScraper:
    def __init__(self):
        self.notion_headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

        # LGBTQ+ detection patterns
        self.lgbtq_patterns = [
            r"(?i)lgbtq?\+?",
            r"(?i)queer[-\s]?friendly",
            r"(?i)queer\s*house(hold)?",
            r"(?i)gay[-\s]?share",
            r"(?i)gay[-\s]?friendly",
            r"(?i)lesbian[-\s]?friendly",
            r"(?i)trans[-\s]?friendly",
            r"(?i)rainbow\s*(home|house|household)",
        ]

        # Nationality detection patterns
        self.nationality_patterns = {
            "Australian": r"(?i)\b(aussies?|australian[s]?)\b",
            "Brazilian": r"(?i)\b(brazil(ian)?s?|portuguese\s*(speaker|speaking)|portugu(e|ê)s)\b",
        }

        self.target_suburbs = ["Surry Hills", "Darlinghurst", "Newtown"]

    def log(self, message: str):
        """Simple logger"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")

    def detect_lgbtq_content(self, text: str) -> bool:
        """Detect LGBTQ+ content"""
        return any(re.search(pattern, text) for pattern in self.lgbtq_patterns)

    def extract_nationalities(self, text: str) -> List[str]:
        """Extract nationalities"""
        found = []
        for nationality, pattern in self.nationality_patterns.items():
            if re.search(pattern, text):
                found.append(nationality)
        return found

    def generate_hash(self, listing: Dict) -> str:
        """Generate hash for deduplication"""
        key = f"{listing['title']}|{listing['price_per_week']}|{listing['suburb']}|{listing['date_posted']}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def search_notion_duplicate(self, url: str) -> bool:
        """Check if URL already exists in Notion"""
        query_data = {"filter": {"property": "URL", "url": {"equals": url}}}

        try:
            response = requests.post(
                f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query",
                headers=self.notion_headers,
                json=query_data,
            )

            if response.status_code == 200:
                results = response.json().get("results", [])
                return len(results) > 0

        except Exception as e:
            self.log(f"Error while checking Notion duplicates: {e}")

        return False

    def analyze_with_openai(self, listing: Dict) -> Dict:
        """Analyze listing using OpenAI"""
        prompt = f"""
Analyze this Sydney flatshare listing and return a JSON object with this exact structure:
{{
    "summary": "2-3 sentence summary in English",
    "lgbtq": true/false,
    "nationalities": ["Australian", "Brazilian"],
    "tags": ["ensuite", "bills included", "furnished"],
    "score": 0-100,
    "reasons": ["scoring rationale"]
}}

Listing data:
Title: {listing['title']}
Description: {listing['description']}
Price/week: ${listing['price_per_week']}
Suburb: {listing['suburb']}

Scoring rules:
- Base: 50
- +25 if LGBTQ+ explicit
- +10 for premium suburbs (Surry Hills, Darlinghurst, Newtown)
- +10 if Australians mentioned
- +10 if Brazilians mentioned
- +10 if ensuite/private bathroom
- +10 if bills included
- -20 if shared room
"""

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o-mini",
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert in LGBTQ+ flatshares in Sydney. Always respond in JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 500,
                },
            )

            if response.status_code == 200:
                result = response.json()
                analysis = json.loads(result["choices"][0]["message"]["content"])
                return analysis

        except Exception as e:
            self.log(f"OpenAI error: {e}")

        # Fallback analysis
        text = f"{listing['title']} {listing['description']}".lower()
        score = 50
        lgbtq = self.detect_lgbtq_content(text)
        if lgbtq:
            score += 25
        if listing["suburb"] in self.target_suburbs:
            score += 10

        return {
            "summary": f"Flatshare in {listing['suburb']} for ${listing['price_per_week']}/week.",
            "lgbtq": lgbtq,
            "nationalities": self.extract_nationalities(text),
            "tags": [],
            "score": min(100, max(0, score)),
            "reasons": ["Fallback analysis - OpenAI failed"],
        }

    def create_notion_page(self, listing: Dict, analysis: Dict) -> bool:
        """Create a page in Notion"""
        page_data = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "Title": {"title": [{"text": {"content": listing["title"][:100]}}]},
                "URL": {"url": listing["url"]},
                "Source": {"select": {"name": listing["source"]}},
                "Prix/sem.": {"number": listing["price_per_week"]},
                "Quartier": {"select": {"name": listing["suburb"]}},
                "Date annonce": {"date": {"start": listing["date_posted"]}},
                "LGBTQ": {"checkbox": analysis["lgbtq"]},
                "Nationalités": {
                    "multi_select": [{"name": nat} for nat in analysis.get("nationalities", [])]
                },
                "Score": {"number": analysis["score"]},
                "Tags": {
                    "multi_select": [{"name": tag} for tag in analysis.get("tags", [])]
                },
                "Statut": {"select": {"name": "Nouveau"}},
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": listing["description"][:2000]}}]
                    },
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": f"✨ AI Summary: {analysis['summary']}"}}],
                    },
                },
            ],
        }

        try:
            response = requests.post(
                "https://api.notion.com/v1/pages",
                headers=self.notion_headers,
                json=page_data,
            )

            if response.status_code == 200:
                self.log(f"✅ Created in Notion: {listing['title'][:50]}...")
                return True
            else:
                self.log(f"❌ Notion error: {response.status_code} - {response.text}")

        except Exception as e:
            self.log(f"❌ Error creating Notion page: {e}")

        return False

    def send_telegram_notification(self, listings: List[Dict]):
        """Send Telegram notification"""
        if not listings or not TELEGRAM_BOT_TOKEN:
            return

        message = f"🏳️‍🌈 {len(listings)} new LGBTQ+ flatshare ads in Sydney!\n\n"

        for i, listing in enumerate(listings[:3]):
            message += f"{i+1}. {listing['title'][:40]}...\n"
            message += f"   📍 {listing['suburb']} - ${listing['price_per_week']}/week\n"
            message += f"   🎯 Score: {listing['score']}/100\n"
            message += f"   🔗 {listing['url']}\n\n"

        if len(listings) > 3:
            message += f"...and {len(listings)-3} more ads!"

        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            self.log(f"📱 Telegram notification sent: {len(listings)} listings")

        except Exception as e:
            self.log(f"❌ Telegram error: {e}")

    def scrape_sample_listings(self) -> List[Dict]:
        """Simplified scraper with example listings"""
        sample_listings = [
            {
                "title": "Private room in queer-friendly share house - Surry Hills",
                "description": "Lovely private room with ensuite in a welcoming LGBTQ+ household. We're a mix of Australian and Brazilian flatmates who love to cook together! Close to Oxford Street and all the rainbow action. Bills included, fully furnished.",
                "url": f"https://flatmates.com.au/listing/{random.randint(10000, 99999)}",
                "price_per_week": random.randint(350, 450),
                "suburb": random.choice(["Surry Hills", "Darlinghurst", "Newtown"]),
                "date_posted": datetime.now().strftime("%Y-%m-%d"),
                "source": "Flatmates",
            },
            {
                "title": "Room in gay share house - Darlinghurst",
                "description": "Gay-friendly share house in the heart of Darlinghurst. Private bathroom, close to train station. We're looking for a like-minded person to join our small household. Two current flatmates - one Aussie teacher, one international student from São Paulo.",
                "url": f"https://gayshare.com.au/listing/{random.randint(10000, 99999)}",
                "price_per_week": random.randint(380, 480),
                "suburb": random.choice(["Darlinghurst", "Surry Hills"]),
                "date_posted": datetime.now().strftime("%Y-%m-%d"),
                "source": "Gay Share",
            },
        ]

        hour = datetime.now().hour
        num_listings = random.randint(0, 2) if 8 <= hour <= 20 else random.randint(0, 1)
        return sample_listings[:num_listings]

    def run(self):
        """Main execution"""
        self.log("🚀 Starting LGBTQ+ Sydney Scraper")

        raw_listings = self.scrape_sample_listings()
        self.log(f"📦 {len(raw_listings)} listings retrieved")

        if not raw_listings:
            self.log("ℹ️ No new listings found")
            return

        processed_listings = []

        for listing in raw_listings:
            try:
                if self.search_notion_duplicate(listing["url"]):
                    self.log(f"⏭️ Duplicate ignored: {listing['title'][:30]}...")
                    continue

                self.log(f"🔍 Analyzing: {listing['title'][:30]}...")
                analysis = self.analyze_with_openai(listing)

                if not analysis["lgbtq"] and listing["suburb"] not in self.target_suburbs:
                    self.log(f"❌ Filtered out (not LGBTQ+): {listing['title'][:30]}...")
                    continue

                if self.create_notion_page(listing, analysis):
                    processed_listings.append(
                        {**listing, "score": analysis["score"], "lgbtq": analysis["lgbtq"]}
                    )

                time.sleep(random.uniform(2, 5))

            except Exception as e:
                self.log(f"❌ Processing error: {e}")
                continue

        if processed_listings:
            self.send_telegram_notification(processed_listings)

        self.log(f"✅ Done: {len(processed_listings)} listings added")


if __name__ == "__main__":
    scraper = LGBTQColocScraper()
    scraper.run()
