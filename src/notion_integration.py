import os
import requests
from datetime import datetime

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def create_notion_page(listing, analysis):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    page_data = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Ad Title": {"title": [{"text": {"content": listing["title"]}}]},
            "Source": {"select": {"name": listing.get("source", "Flatmates")}},
            "Publish date": {"date": {"start": listing["date_posted"]}},
            "Location": {"select": {"name": listing["suburb"]}},
            "Rent/week": {"number": listing["price_per_week"]},
            "Summary": {"rich_text": [{"text": {"content": analysis["summary"][:500]}}]},
            "Score": {"number": analysis.get("score", 0)},
            "Tags": {"multi_select": [{"name": t} for t in analysis.get("tags", [])]},
            "Status": {"status": {"name": "New"}},
            "Link": {"url": listing["url"]},
        },
    }

    res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=page_data)
    if res.status_code != 200:
        print(f"❌ Notion error: {res.status_code} - {res.text}")
    else:
        print(f"✅ Notion page created: {listing['title']}")
