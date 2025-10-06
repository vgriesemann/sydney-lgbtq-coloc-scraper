#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LGBTQ+ Sydney Flatshare Scraper
Automated search system for LGBTQ+ flatshare ads in Sydney
"""

import os
import re
import time
import json
import random
import requests
from datetime import datetime
from typing import Dict, List
from bs4 import BeautifulSoup

# === CONFIGURATION ===
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

        self.lgbtq_patterns = [
            r"(?i)lgbtq?\+?",
            r"(?i)queer[-\s]?friendly",
            r"(?i)gay[-\s]?share",
            r"(?i)gay[-\s]?friendly",
            r"(?i)rainbow\s*(home|house|household)",
        ]

        self.nationality_patterns = {
            "Australian": r"(?i)\b(aussies?|australian[s]?)\b",
            "Brazilian": r"(?i)\b(brazil(ian)?s?|portuguese)\b",
        }

        self.target_suburbs = ["Surry Hills", "Darlinghurst", "Newtown"]

    def log(self, msg: str):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    # === IMAGE FETCHER ===
    def get_first_image_url(self, listing_url: str) -> str:
        """Extract the first image URL from the listing page"""
        try:
            response = requests.get(listing_url, timeout=10)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, "html.parser")
            img = soup.find("img", {"class": "listing-image"}) or soup.find("img")
            if img and img.get("src"):
                return img["src"]
        except Exception as e:
            self.log(f"⚠️ Error fetching image: {e}")
        return None

    # === ANALYSIS ===
    def detect_lgbtq_content(self, text: str) -> bool:
        return any(re.search(p, text) for p in self.lgbtq_patterns)

    def extract_nationalities(self, text: str) -> List[str]:
        found = []
        for n, p in self.nationality_patterns.items():
            if re.search(p, text):
                found.append(n)
        return found

    def analyze_with_openai(self, listing: Dict) -> Dict:
        """Analyse ad text with OpenAI"""
        prompt = f"""
Analyze this flatshare listing in Sydney and return a JSON object with this structure:
{{
  "summary": "2-3 sentences summary in English",
  "lgbtq": true/false,
  "nationalities": ["Australian", "Brazilian"],
  "tags": ["ensuite", "bills included", "furnished"],
  "score": 0-100,
  "reasons": ["why this score"]
}}

Ad data:
Title: {listing['title']}
Description: {listing['description']}
Price/week: ${listing['price_per_week']}
Location: {listing['suburb']}
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
                            "content": "You are an assistant that evaluates LGBTQ+ flatshare ads in Sydney and outputs only valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                },
            )

            if response.status_code == 200:
                data = response.json()
                analysis = json.loads(data["choices"][0]["message"]["content"])
                return analysis

        except Exception as e:
            self.log(f"⚠️ OpenAI error: {e}")

        text = (listing["title"] + " " + listing["description"]).lower()
        lgbtq = self.detect_lgbtq_content(text)
        score = 50 + (25 if lgbtq else 0)
        if listing["suburb"] in self.target_suburbs:
            score += 10
        return {
            "summary": f"Flatshare in {listing['suburb']} for ${listing['price_per_week']}/week.",
            "lgbtq": lgbtq,
            "nationalities": self.extract_nationalities(text),
            "tags": [],
            "score": min(100, score),
            "reasons": ["Fallback analysis used"],
        }

    # === NOTION INTEGRATION ===
    def create_notion_page(self, listing: Dict, analysis: Dict) -> bool:
        """Send data to Notion"""

        page_data = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "Ad Title": {"title": [{"text": {"content": listing["title"][:100]}}]},
                "Source": {"select": {"name": listing["source"]}},
                "Publish date": {"date": {"start": listing["date_posted"]}},
                "Location": {"select": {"name": listing["suburb"]}},
                "Rent/week": {"number": listing["price_per_week"]},
                "Description": {
                    "rich_text": [{"text": {"content": listing["description"][:1800]}}]
                },
                "Summary": {
                    "rich_text": [{"text": {"content": analysis["summary"][:500]}}]
                },
                "Link": {"url": listing["url"]},
                "Image URL": {"url": listing.get("image_url")},
                "Score": {"number": analysis["score"]},
                "Nationalities": {
                    "multi_select": [{"name": n} for n in analysis.get("nationalities", [])]
                },
                "Status": {"status": {"name": "Not started"}},
            },
        }

        try:
            res = requests.post(
                "https://api.notion.com/v1/pages",
                headers=self.notion_headers,
                json=page_data,
            )
            if res.status_code == 200:
                self.log(f"✅ Added to Notion: {listing['title']}")
                return True
            else:
                self.log(f"❌ Notion error: {res.status_code} - {res.text}")
        except Exception as e:
            self.log(f"❌ Exception while pushing to Notion: {e}")
        return False

    # === TELEGRAM ===
    def send_telegram_notification(self, listings: List[Dict]):
        if not TELEGRAM_BOT_TOKEN or not listings:
            return
        message = f"🏳️‍🌈 {len(listings)} new LGBTQ+ flatshare ads!\n\n"
        for ad in listings[:3]:
            message += f"🏠 {ad['title'][:40]}...\n📍 {ad['suburb']} - ${ad['price_per_week']}/week\n🔗 {ad['url']}\n\n"
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            )
            self.log("📩 Telegram notification sent")
        except Exception as e:
            self.log(f"⚠️ Telegram error: {e}")

    # === SAMPLE SCRAPER ===
    def scrape_sample_listings(self) -> List[Dict]:
        """Temporary fake scraper returning mock listings"""
        return [
            {
                "title": "Queer-friendly ensuite in Surry Hills",
                "description": "Spacious room in a welcoming LGBTQ+ household, near Oxford Street. Bills included, fully furnished.",
                "url": "https://flatmates.com.au/listing/12345",
                "price_per_week": random.randint(350, 480),
                "suburb": "Surry Hills",
                "date_posted": datetime.now().strftime("%Y-%m-%d"),
                "source": "Flatmates",
            }
        ]

    # === EMAIL GENERATION ===
    def generate_html_email(self, listings):
        html_blocks = []
        for listing in listings:
            html_blocks.append(f"""
            <div style='border:1px solid #ddd; border-radius:8px; overflow:hidden; margin-bottom:20px;'>
              <img src="{listing.get('image_url', '')}" style='width:100%; height:auto;'>
              <div style='padding:16px;'>
                <h3 style='margin-top:0;'>{listing['title']}</h3>
                <p><strong>${listing['price_per_week']}/week</strong> · {listing['suburb']}</p>
                <p>{listing.get('summary','')}</p>
                <a href="{listing['url']}" style='color:#3366cc;'>View listing</a>
              </div>
            </div>
            """)
        html = f"""
        <html><body style='font-family:Arial,sans-serif; background:#fafafa; padding:20px;'>
          <h2>🏳️‍🌈 New LGBTQ+ Flatshare listings – {datetime.now().strftime('%B %d, %Y')}</h2>
          {''.join(html_blocks)}
          <p style='color:#999;font-size:12px;'>Generated automatically by your Sydney LGBTQ+ Scraper ✨</p>
        </body></html>
        """
        with open("daily_digest.html", "w", encoding="utf-8") as f:
            f.write(html)
        self.log("📧 HTML email generated → daily_digest.html")

    # === MAIN RUN ===
    def run(self):
        self.log("🚀 Starting LGBTQ+ Sydney Scraper")
        listings = self.scrape_sample_listings()
        self.log(f"📦 {len(listings)} listing(s) retrieved")

        processed = []
        for listing in listings:
            try:
                listing["image_url"] = self.get_first_image_url(listing["url"])
                self.log(f"🔍 Analyzing: {listing['title']}")
                analysis = self.analyze_with_openai(listing)
                if self.create_notion_page(listing, analysis):
                    processed.append({**listing, **analysis})
                time.sleep(random.uniform(2, 5))
            except Exception as e:
                self.log(f"⚠️ Processing error: {e}")

        if processed:
            self.send_telegram_notification(processed)
            self.generate_html_email(processed)

        self.log(f"✅ Done. {len(processed)} listing(s) added.")


if __name__ == "__main__":
    scraper = LGBTQColocScraper()
    scraper.run()
