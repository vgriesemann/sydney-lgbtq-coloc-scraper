import os
import requests
import json

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def analyze_listing_with_openai(listing):
    prompt = f"""
Analyze this flatshare listing and return JSON:
{{
  "summary": "2-3 sentence summary in English",
  "tags": ["ensuite", "bills included", "furnished"],
  "score": 0-100,
  "reasons": ["why this listing is good for LGBTQ+ audience"]
}}

Title: {listing['title']}
Description: {listing['description']}
Price/week: {listing['price_per_week']}
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
                    {"role": "system", "content": "You are a data analyst for Sydney LGBTQ+ housing."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
            },
        )
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        print(f"⚠️ OpenAI error: {e}")
        return {"summary": "No summary available", "tags": [], "score": 0, "reasons": []}
