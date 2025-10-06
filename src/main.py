#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🏳️‍🌈 Sydney Housing Watch — Full pipeline
Scraper → OpenAI → Notion → Gmail
"""

import os
from dotenv import load_dotenv
from src.flatshare_scraper import scrape_flatmates_listings
from src.openai_analyzer import analyze_listing_with_openai
from src.notion_integration import create_notion_page
from src.email_sender import send_html_email_dynamic

load_dotenv()

def run_pipeline():
    listings = scrape_flatmates_listings(limit=3)
    if not listings:
        print("❌ No listings found.")
        return

    for listing in listings:
        print(f"\n🔍 Processing: {listing['title']} — {listing['suburb']}")
        analysis = analyze_listing_with_openai(listing)
        create_notion_page(listing, analysis)
        send_html_email_dynamic(
            "valentin.griesemann@gmail.com",
            f"🏳️‍🌈 {listing['suburb']} — {listing['title']}",
            "src/AutoMail.html",
            {
                **listing,
                "summary": analysis.get("summary", ""),
                "reasoning": ", ".join(analysis.get("reasons", [])),
                "tags": analysis.get("tags", []),
                "similar_listings": [],
            },
        )

    print("✅ All listings processed.")

if __name__ == "__main__":
    run_pipeline()
