import os
import base64
import requests
from io import BytesIO
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Gmail API scope (send-only)
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# === ✉️ Main Function ===
def send_html_email_dynamic(to_email, subject, html_template_path, listing_data):
    """
    Sends a personalized HTML email replacing placeholders in the template
    with dynamic listing data (title, image, tags, price, etc.)
    """

    # --- 1️⃣ Load Google credentials ---
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)

    # --- 2️⃣ Load HTML template ---
    if not os.path.exists(html_template_path):
        raise FileNotFoundError(f"Template not found: {html_template_path}")

    with open(html_template_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # --- 3️⃣ Currency conversions ---
    price_per_week = float(listing_data.get("price_per_week", 0))
    price_per_month_aud = round(price_per_week * 4.33, 1)
    eur_conversion_rate = 0.61  # Approximate (you can replace with live API later)
    price_per_month_eur = round(price_per_month_aud * eur_conversion_rate, 1)

    # --- 4️⃣ Build “similar listings” section dynamically ---
    similar_html = ""
    if "similar_listings" in listing_data and listing_data["similar_listings"]:
        for item in listing_data["similar_listings"]:
            similar_html += f"""
            <tr>
                <td style='width:90px; padding:8px 0 8px 24px;'>
                    <img src='{get_base64_image(item.get("thumbnail_url", ""))}' 
                         width='80' height='80' style='object-fit:cover; border-radius:8px;'>
                </td>
                <td style='padding:8px 24px; vertical-align:middle;'>
                    <a href='{item.get("url", "#")}' 
                       style='font-size:15px; color:#007aff; text-decoration:none; font-weight:600;'>
                        {item.get("title", "Flatshare")}
                    </a><br>
                    <span style='font-size:13px; color:#666;'>
                        {item.get("suburb", "Sydney")} — ${item.get("price_per_week", "N/A")}/week
                    </span>
                </td>
            </tr>
            """
    else:
        similar_html = "<tr><td style='padding:8px 24px;'><i>No other listings right now 🌆</i></td></tr>"

    # --- 5️⃣ Replace placeholders in HTML ---
    replacements = {
        "{{openai_subject}}": listing_data.get("title", "Sydney Flatshare"),
        "{{Quartier}}": listing_data.get("suburb", "Sydney"),
        "{{price_per_week}}": str(price_per_week),
        "{{price_per_month_aud}}": str(price_per_month_aud),
        "{{price_per_month_eur}}": str(price_per_month_eur),
        "{{date_posted}}": listing_data.get("date_posted", "N/A"),
        "{{tags}}": ", ".join(listing_data.get("tags", [])),
        "{{summary}}": listing_data.get("summary", ""),
        "{{reasoning}}": listing_data.get("reasoning", ""),
        "{{url}}": listing_data.get("url", "#"),
        "{{contact_email}}": listing_data.get("contact_email", "owner@example.com"),
        "{{similar_listings}}": similar_html,
    }

    for key, value in replacements.items():
        html_content = html_content.replace(key, str(value))

    # --- 6️⃣ Build MIME email object ---
    message = MIMEText(html_content, "html", "utf-8")
    message["to"] = to_email
    message["subject"] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    # --- 7️⃣ Send email via Gmail API ---
    try:
        send_message = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw_message})
            .execute()
        )
        print(f"✅ Email sent to {to_email}")
        return send_message
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return None