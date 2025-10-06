#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LGBTQ+ Sydney Flatshare Scraper (multi-sites + images + email HTML)
"""

import os
import re
import time
import json
import hashlib
import random
import requests
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from bs4 import BeautifulSoup

# === CONFIGURATION ===
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en,en-US;q=0.9,fr;q=0.8",
    "Connection": "close",
}

TIMEOUT = 20
MAX_PER_SITE = 8  # limite soft par site pour rester gentil
SESSION = requests.Session()
SESSION.headers.update(DEFAULT_HEADERS)


@dataclass
class Listing:
    title: str
    description: str
    url: str
    price_per_week: Optional[int]
    suburb: str
    date_posted: str  # ISO date
    source: str
    image_url: Optional[str] = None


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
            r"(?i)queer\s*house(hold)?",
            r"(?i)gay[-\s]?share",
            r"(?i)gay[-\s]?friendly",
            r"(?i)lesbian[-\s]?friendly",
            r"(?i)trans[-\s]?friendly",
            r"(?i)rainbow\s*(home|house|household)",
        ]

        self.nationality_patterns = {
            "Australian": r"(?i)\b(aussies?|australian[s]?)\b",
            "Brazilian": r"(?i)\b(brazil(ian)?s?|portuguese|portugu[eê]s)\b",
        }

        self.target_suburbs = ["Surry Hills", "Darlinghurst", "Newtown"]

    # -------------------- utils --------------------
    def log(self, msg: str):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def detect_lgbtq_content(self, text: str) -> bool:
        return any(re.search(p, text) for p in self.lgbtq_patterns)

    def extract_nationalities(self, text: str) -> List[str]:
        found = []
        for n, p in self.nationality_patterns.items():
            if re.search(p, text):
                found.append(n)
        return found

    def _price_to_int(self, text: str) -> Optional[int]:
        if not text:
            return None
        m = re.search(r"(\d{2,4})", text.replace(",", ""))
        return int(m.group(1)) if m else None

    def _first_text(self, node) -> str:
        return node.get_text(strip=True) if node else ""

    # -------------------- OpenAI --------------------
    def analyze_with_openai(self, listing: Dict) -> Dict:
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
Price/week: ${listing.get('price_per_week')}
Location: {listing['suburb']}
"""
        try:
            res = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o-mini",
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "You evaluate LGBTQ+ flatshare ads in Sydney and output only valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
                timeout=TIMEOUT,
            )
            if res.status_code == 200:
                data = res.json()
                return json.loads(data["choices"][0]["message"]["content"])
        except Exception as e:
            self.log(f"⚠️ OpenAI error: {e}")

        # Fallback simple
        text = (listing["title"] + " " + listing["description"]).lower()
        lgbtq = self.detect_lgbtq_content(text)
        score = 50 + (25 if lgbtq else 0)
        if listing["suburb"] in self.target_suburbs:
            score += 10
        return {
            "summary": f"Flatshare in {listing['suburb']} for ${listing.get('price_per_week')}/week.",
            "lgbtq": lgbtq,
            "nationalities": self.extract_nationalities(text),
            "tags": [],
            "score": min(100, max(0, score)),
            "reasons": ["Fallback analysis used"],
        }

    # -------------------- Notion --------------------
    def create_notion_page(self, listing: Dict, analysis: Dict) -> bool:
        props = {
            # adapte à ta DB FR/EN si besoin
            "Ad Title": {"title": [{"text": {"content": listing["title"][:100]}}]},
            "Source": {"select": {"name": listing["source"]}},
            "Publish date": {"date": {"start": listing["date_posted"]}},
            "Location": {"select": {"name": listing["suburb"]}},
            "Rent/week": {"number": listing.get("price_per_week")},
            "Description": {
                "rich_text": [{"text": {"content": listing["description"][:1800]}}]
            },
            "Summary": {
                "rich_text": [{"text": {"content": analysis["summary"][:500]}}]
            },
            "Link": {"url": listing["url"]},
            "Score": {"number": analysis["score"]},
            "Nationalities": {
                "multi_select": [{"name": n} for n in analysis.get("nationalities", [])]
            },
            "Status": {"status": {"name": "Not started"}},  # doit exister dans ta DB
        }

        # Ajoute une propriété URL "Image" si tu l’as créée
        if listing.get("image_url"):
            props["Image"] = {"url": listing["image_url"]}

        page_data = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": props,
        }

        # Définir la cover Notion si image
        if listing.get("image_url"):
            page_data["cover"] = {
                "type": "external",
                "external": {"url": listing["image_url"]},
            }

        try:
            res = requests.post(
                "https://api.notion.com/v1/pages",
                headers=self.notion_headers,
                json=page_data,
                timeout=TIMEOUT,
            )
            if res.status_code == 200:
                self.log(f"✅ Added to Notion: {listing['title']}")
                return True
            else:
                self.log(f"❌ Notion error: {res.status_code} - {res.text}")
        except Exception as e:
            self.log(f"❌ Exception while pushing to Notion: {e}")
        return False

    # -------------------- Telegram --------------------
    def send_telegram_notification(self, listings: List[Dict]):
        if not TELEGRAM_BOT_TOKEN or not listings:
            return
        message = f"🏳️‍🌈 {len(listings)} new LGBTQ+ flatshare ads!\n\n"
        for ad in listings[:5]:
            message += (
                f"🏠 {ad['title'][:60]}\n"
                f"📍 {ad['suburb']} — ${ad.get('price_per_week')}/week\n"
                f"🔗 {ad['url']}\n\n"
            )
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": message},
                timeout=TIMEOUT,
            )
            self.log("📩 Telegram notification sent")
        except Exception as e:
            self.log(f"⚠️ Telegram error: {e}")

    # -------------------- Email HTML (génération) --------------------
    def build_html_email(self, listings: List[Dict]) -> str:
        # Modèle simple, compatible Gmail/Outlook (pas d’images inline pour l’instant)
        rows = []
        for ad in listings:
            img = (
                f'<img src="{ad.get("image_url")}" alt="" width="120" '
                f'style="border-radius:8px;display:block;">'
                if ad.get("image_url")
                else ""
            )
            price = f"${ad.get('price_per_week')}/week" if ad.get("price_per_week") else ""
            rows.append(
                f"""
<tr>
  <td style="padding:12px;border-bottom:1px solid #eee;vertical-align:top;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td style="padding-right:12px;">{img}</td>
        <td>
          <a href="{ad['url']}" style="font-size:16px;font-weight:600;color:#0b5cff;text-decoration:none;">
            {ad['title']}
          </a>
          <div style="font-size:13px;color:#444;margin:6px 0;">{ad['suburb']} · {price} · {ad['source']}</div>
          <div style="font-size:13px;color:#666;line-height:1.4;">{ad['description'][:220]}…</div>
        </td>
      </tr>
    </table>
  </td>
</tr>
"""
            )

        html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>LGBTQ+ Sydney — New Listings</title>
</head>
<body style="margin:0;padding:0;background:#f6f8fb;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
    <tr>
      <td align="center" style="padding:24px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="640" style="background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.08);overflow:hidden;">
          <tr>
            <td style="padding:20px 24px;background:#0b5cff;color:#fff;font-size:18px;font-weight:700;">
              🏳️‍🌈 LGBTQ+ Sydney · New Listings
            </td>
          </tr>
          {''.join(rows)}
          <tr>
            <td style="padding:14px 24px;color:#777;font-size:12px;">
              You receive this recap because you enabled alerts. Change frequency in GitHub/Notion.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
        return html

    # -------------------- Scrapers --------------------
    def _safe_get(self, url: str) -> Optional[BeautifulSoup]:
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                self.log(f"ℹ️ {url} -> {r.status_code}")
                return None
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            self.log(f"⚠️ GET fail {url}: {e}")
            return None

    def scrape_gayshare(self) -> List[Listing]:
        """Gay Share AU — pages publiques basiques"""
        # Page liste Sydney (approximatif, selectors susceptibles d’évoluer)
        url = "https://www.gayshare.com.au/rooms/sydney"
        soup = self._safe_get(url)
        out = []
        if not soup:
            return out

        cards = soup.select("article, .listing, .result, .card")
        for c in cards[:MAX_PER_SITE]:
            a = c.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            if href.startswith("/"):
                href = "https://www.gayshare.com.au" + href

            title = self._first_text(c.find(["h2", "h3"])) or self._first_text(a)
            desc = self._first_text(c.find("p"))
            price_text = self._first_text(c.find(class_=re.compile("price", re.I)))
            suburb = self._first_text(c.find(class_=re.compile("suburb|area|location", re.I)))
            img = c.find("img")
            img_url = None
            if img and img.get("src"):
                img_url = img["src"]
                if img_url.startswith("//"):
                    img_url = "https:" + img_url

            out.append(
                Listing(
                    title=title or "Room — Gay Share",
                    description=desc or "",
                    url=href,
                    price_per_week=self._price_to_int(price_text),
                    suburb=suburb or "Sydney",
                    date_posted=datetime.now().strftime("%Y-%m-%d"),
                    source="Gay Share",
                    image_url=img_url,
                )
            )
        self.log(f"🌈 GayShare: {len(out)}")
        return out

    def scrape_gumtree(self) -> List[Listing]:
        """Gumtree — Shared accommodation Sydney (list publique)"""
        # Catégorie “Flatshare & Houseshare” à Sydney — URL indicative
        url = "https://www.gumtree.com.au/s-flatshare-houseshare/sydney/c18294l3003435"
        soup = self._safe_get(url)
        out = []
        if not soup:
            return out

        cards = soup.select("article, .user-ad-collection .user-ad-row, .search-listing")
        for c in cards[:MAX_PER_SITE]:
            a = c.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            if href.startswith("/"):
                href = "https://www.gumtree.com.au" + href

            title = self._first_text(c.find(["h2", "h3"])) or self._first_text(a)
            desc = self._first_text(c.find("p"))
            price_text = self._first_text(c.find(class_=re.compile("price", re.I)))
            suburb = self._first_text(c.find(class_=re.compile("location|suburb|area", re.I)))

            # image
            img_url = None
            img = c.find("img")
            if img:
                img_url = img.get("data-src") or img.get("src")
                if img_url and img_url.startswith("//"):
                    img_url = "https:" + img_url

            out.append(
                Listing(
                    title=title or "Room — Gumtree",
                    description=desc or "",
                    url=href,
                    price_per_week=self._price_to_int(price_text),
                    suburb=suburb or "Sydney",
                    date_posted=datetime.now().strftime("%Y-%m-%d"),
                    source="Gumtree",
                    image_url=img_url,
                )
            )
        self.log(f"🟢 Gumtree: {len(out)}")
        return out

    def scrape_flatmates(self) -> List[Listing]:
        """Flatmates — pages publiques (liste ville) *souvent protégé/besoin login*"""
        # URL publique générique (peut nécessiter JS/login -> best effort)
        url = "https://flatmates.com.au/rooms/sydney"
        soup = self._safe_get(url)
        out = []
        if not soup:
            return out

        cards = soup.select("article, .ListingCard, .card")
        for c in cards[:MAX_PER_SITE]:
            a = c.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            if href.startswith("/"):
                href = "https://flatmates.com.au" + href

            title = self._first_text(c.find(["h2", "h3"])) or self._first_text(a)
            desc = self._first_text(c.find("p"))
            price_text = self._first_text(c.find(class_=re.compile("price", re.I)))
            suburb = self._first_text(c.find(class_=re.compile("suburb|location|area", re.I)))
            img = c.find("img")
            img_url = None
            if img:
                img_url = img.get("data-src") or img.get("src")
                if img_url and img_url.startswith("//"):
                    img_url = "https:" + img_url

            out.append(
                Listing(
                    title=title or "Room — Flatmates",
                    description=desc or "",
                    url=href,
                    price_per_week=self._price_to_int(price_text),
                    suburb=suburb or "Sydney",
                    date_posted=datetime.now().strftime("%Y-%m-%d"),
                    source="Flatmates",
                    image_url=img_url,
                )
            )
        self.log(f"🔵 Flatmates: {len(out)}")
        return out

    def scrape_flatmate_finders(self) -> List[Listing]:
        """Flatmate Finders — liste Sydney (best effort)"""
        url = "https://www.flatmatefinders.com.au/rooms/sydney"
        soup = self._safe_get(url)
        out = []
        if not soup:
            return out

        cards = soup.select("article, .result, .card, .listing")
        for c in cards[:MAX_PER_SITE]:
            a = c.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            if href.startswith("/"):
                href = "https://www.flatmatefinders.com.au" + href
            title = self._first_text(c.find(["h2", "h3"])) or self._first_text(a)
            desc = self._first_text(c.find("p"))
            price_text = self._first_text(c.find(class_=re.compile("price", re.I)))
            suburb = self._first_text(c.find(class_=re.compile("suburb|location|area", re.I)))
            img = c.find("img")
            img_url = None
            if img:
                img_url = img.get("data-src") or img.get("src")
                if img_url and img_url.startswith("//"):
                    img_url = "https:" + img_url

            out.append(
                Listing(
                    title=title or "Room — Flatmate Finders",
                    description=desc or "",
                    url=href,
                    price_per_week=self._price_to_int(price_text),
                    suburb=suburb or "Sydney",
                    date_posted=datetime.now().strftime("%Y-%m-%d"),
                    source="Flatmate Finders",
                    image_url=img_url,
                )
            )
        self.log(f"🟣 FlatmateFinders: {len(out)}")
        return out

    def scrape_roomgo(self) -> List[Listing]:
        """Roomgo AU — Sydney (best effort)"""
        url = "https://au.roomgo.net/sydney-flatshare"
        soup = self._safe_get(url)
        out = []
        if not soup:
            return out

        cards = soup.select("article, .listing, .card, .property")
        for c in cards[:MAX_PER_SITE]:
            a = c.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            if href.startswith("/"):
                href = "https://au.roomgo.net" + href
            title = self._first_text(c.find(["h2", "h3"])) or self._first_text(a)
            desc = self._first_text(c.find("p"))
            price_text = self._first_text(c.find(class_=re.compile("price", re.I)))
            suburb = self._first_text(c.find(class_=re.compile("suburb|location|area", re.I)))
            img = c.find("img")
            img_url = None
            if img:
                img_url = img.get("data-src") or img.get("src")
                if img_url and img_url.startswith("//"):
                    img_url = "https:" + img_url

            out.append(
                Listing(
                    title=title or "Room — Roomgo",
                    description=desc or "",
                    url=href,
                    price_per_week=self._price_to_int(price_text),
                    suburb=suburb or "Sydney",
                    date_posted=datetime.now().strftime("%Y-%m-%d"),
                    source="Roomgo",
                    image_url=img_url,
                )
            )
        self.log(f"🟠 Roomgo: {len(out)}")
        return out

    def scrape_sample_listings(self) -> List[Listing]:
        """Fallback mock si tous les sites échouent (garde l’architecture en vie)"""
        return [
            Listing(
                title="Queer-friendly ensuite in Surry Hills",
                description="Spacious room in a welcoming LGBTQ+ household, near Oxford Street. Bills included, fully furnished.",
                url="https://flatmates.com.au/listing/12345",
                price_per_week=random.randint(350, 480),
                suburb="Surry Hills",
                date_posted=datetime.now().strftime("%Y-%m-%d"),
                source="Flatmates",
                image_url="https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800",
            )
        ]

    # -------------------- run --------------------
    def run(self):
        self.log("🚀 Starting LGBTQ+ Sydney Scraper (multi-sites)")

        # 1) Scrape multi-sites (best effort)
        all_listings: List[Listing] = []
        for fn in [
            self.scrape_gayshare,
            self.scrape_gumtree,
            self.scrape_flatmates,
            self.scrape_flatmate_finders,
            self.scrape_roomgo,
        ]:
            try:
                time.sleep(random.uniform(0.8, 1.6))
                all_listings.extend(fn())
            except Exception as e:
                self.log(f"⚠️ Scraper error {fn.__name__}: {e}")

        if not all_listings:
            self.log("ℹ️ No live listings scraped, using sample.")
            all_listings = self.scrape_sample_listings()

        # 2) Dédup par URL
        uniq = {}
        for ad in all_listings:
            uniq.setdefault(ad.url, ad)
        listings = list(uniq.values())
        self.log(f"📦 {len(listings)} unique listing(s) gathered")

        # 3) Analyse + push Notion
        processed: List[Dict] = []
        for ad in listings:
            try:
                self.log(f"🔍 Analyzing: {ad.title[:80]}")
                analysis = self.analyze_with_openai(
                    {
                        "title": ad.title,
                        "description": ad.description,
                        "price_per_week": ad.price_per_week,
                        "suburb": ad.suburb,
                    }
                )
                payload = {
                    "title": ad.title,
                    "description": ad.description,
                    "url": ad.url,
                    "price_per_week": ad.price_per_week,
                    "suburb": ad.suburb,
                    "date_posted": ad.date_posted,
                    "source": ad.source,
                    "image_url": ad.image_url,
                }
                if self.create_notion_page(payload, analysis):
                    processed.append({**payload, **{"score": analysis["score"]}})
                time.sleep(random.uniform(0.6, 1.2))
            except Exception as e:
                self.log(f"⚠️ Processing error: {e}")

        # 4) Telegram (optionnel)
        if processed:
            self.send_telegram_notification(processed)

        # 5) Email HTML (on génère le HTML, libre à toi de l’envoyer ensuite)
        if processed:
            html = self.build_html_email(processed[:12])
            # Tu peux écrire le fichier pour debug (GitHub Actions -> artifact)
            try:
                os.makedirs("out", exist_ok=True)
                with open("out/latest_email.html", "w", encoding="utf-8") as f:
                    f.write(html)
                self.log("✉️  Email HTML generated at out/latest_email.html")
            except Exception as e:
                self.log(f"⚠️ Email HTML write error: {e}")

        self.log(f"✅ Done. {len(processed)} listing(s) added to Notion.")


if __name__ == "__main__":
    scraper = LGBTQColocScraper()
    scraper.run()
