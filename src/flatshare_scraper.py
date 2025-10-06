import requests
from bs4 import BeautifulSoup
from datetime import datetime

BASE_URL = "https://flatmates.com.au/shares/sydney"

def scrape_flatmates_listings(limit=10):
    listings = []
    print("🧹 Scraping Flatmates...")

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(BASE_URL, headers=headers)
    if response.status_code != 200:
        print(f"❌ Error {response.status_code} fetching Flatmates.")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select("li.FmListingCard__ListingCard-sc-1frgr5r-0")[:limit]

    for card in cards:
        title_tag = card.select_one("h2")
        link_tag = card.select_one("a[href]")
        price_tag = card.select_one(".price")
        suburb_tag = card.select_one(".location")
        image_tag = card.select_one("img")

        title = title_tag.get_text(strip=True) if title_tag else "Untitled"
        url = "https://flatmates.com.au" + link_tag["href"] if link_tag else "#"
        price = price_tag.get_text(strip=True).replace("$", "").replace("/week", "") if price_tag else "0"
        suburb = suburb_tag.get_text(strip=True) if suburb_tag else "Unknown"
        thumbnail = image_tag["src"] if image_tag else None

        listings.append({
            "title": title,
            "url": url,
            "price_per_week": int(price) if price.isdigit() else 0,
            "suburb": suburb,
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "thumbnail_url": thumbnail,
            "source": "Flatmates",
            "description": "Description placeholder (to fetch individually later)"
        })

    print(f"✅ Scraped {len(listings)} listings.")
    return listings
