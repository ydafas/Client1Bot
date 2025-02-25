# === Imports ===
from flask import Flask, request, jsonify
import requests
import os
import logging
import json
from oauth2client.service_account import ServiceAccountCredentials
from gspread import authorize, Worksheet
import datetime

# === App Initialization ===
app = Flask(__name__)

# === Logging Setup ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Configuration ===
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "secure_token")

# Google Sheets Configuration
SPREADSHEET_ID = os.environ.get("GOOGLE_SPREADSHEET_ID", "1PPK-cYGb75IH9uKaUf4IACtpAnINwK-n_TAxj86BRlY")
SHEET_NAME = "Lead and Issue Tracker"

# === Google Sheets Authentication ===
def authenticate_google_sheets():
    google_credentials_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not google_credentials_json:
        raise ValueError("GOOGLE_CREDENTIALS environment variable not set")
    try:
        credentials_dict = json.loads(google_credentials_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in GOOGLE_CREDENTIALS: {str(e)}")
    scope = ['https://www.googleapis.com/auth/spreadsheets']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    logger.info("Successfully authenticated with Google Sheets")
    return creds

# Initialize Google Sheets client
try:
    gc = authorize(authenticate_google_sheets())
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        worksheet = sh.worksheet(SHEET_NAME)
    except Exception as e:
        logger.warning("Sheet '%s' not found, creating new one", SHEET_NAME)
        worksheet = sh.add_worksheet(title=SHEET_NAME, rows="100", cols="20")
        worksheet.append_row(["Sender ID", "Category", "User Name", "Order Number", "Urgency", "Website",
                              "Issue Description", "Email", "Phone", "Company", "Timestamp"])
except Exception as e:
    logger.error("Failed to initialize Google Sheets: %s", str(e))
    gc = None
    worksheet = None

# === Webhook Endpoints ===
@app.route('/webhook', methods=['GET', 'POST'])
def fb_webhook():
    if request.method == 'GET':
        verify_token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if verify_token == VERIFY_TOKEN:
            return challenge
        return "Verification failed", 403

    elif request.method == 'POST':
        data = request.json
        logger.info("Received Meta Webhook Data: %s", data)
        if 'entry' in data:
            for entry in data['entry']:
                if 'messaging' in entry:
                    for messaging_event in entry['messaging']:
                        sender_id = messaging_event['sender']['id']
                        if 'message' in messaging_event:
                            if 'quick_reply' in messaging_event['message']:
                                payload = messaging_event['message']['quick_reply'].get('payload', '').lower().strip()
                                logger.info("Processing quick reply payload: %s for sender_id: %s", payload, sender_id)
                                process_message(sender_id, payload)
                            else:
                                message_text = messaging_event['message'].get('text', '').lower().strip()
                                logger.info("Processing message text: %s for sender_id: %s", message_text, sender_id)
                                process_message(sender_id, message_text)
        return "EVENT_RECEIVED", 200

# === Fetch Managed Pages (For API Testing, Remove After Meta Approval) ===
def fetch_managed_pages(sender_id):
    """
    Retrieves the list of Facebook pages a user manages.
    This function is ONLY for API testing and should be removed after Meta approval.
    """
    if not FB_PAGE_TOKEN:
        logger.warning("FB_PAGE_TOKEN not set. Cannot fetch pages.")
        send_message(sender_id, "Error: Missing API token.")
        return

    # Fetch user-managed pages
    url = f"https://graph.facebook.com/v20.0/me/accounts?fields=name,id,category,fan_count&access_token={FB_PAGE_TOKEN}"
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers)
        data = response.json()

        if "error" in data:
            error_message = data["error"].get("message", "Unknown error")
            logger.error("Facebook API Error: %s", error_message)
            send_message(sender_id, f"🚨 Facebook API Error: {error_message}")
            return

        pages = data.get("data", [])
        if not pages:
            send_message(sender_id, "No pages found for this account.")
            return

        # Format response for user
        page_info = "\n".join([f"📌 Name: {p['name']}\n🆔 ID: {p['id']}\n📊 Category: {p.get('category', 'N/A')}\n👍 Fans: {p.get('fan_count', 'N/A')}" for p in pages])
        send_message(sender_id, f"✅ **Your Managed Pages:**\n{page_info}")

    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch managed pages: %s", str(e))
        send_message(sender_id, "An error occurred while fetching pages. Try again later.")

# === Process Incoming Messages ===
def process_message(sender_id, message):
    if message == "page_info":
        fetch_managed_pages(sender_id)
    elif message in ["hi", "hello", "start"]:
        send_message(sender_id, "Welcome! How can I assist you?", quick_replies=[
            {"title": "Services", "payload": "services"},
            {"title": "FAQs", "payload": "faq"},
            {"title": "Support", "payload": "support"},
            {"title": "Sales", "payload": "sales"},
            {"title": "Contact Us", "payload": "contact"},
        ])
    else:
        send_message(sender_id, "Try selecting an option or type 'page_info'.")

# === Send Messages ===
def send_message(sender_id, text, quick_replies=None):
    if FB_PAGE_TOKEN:
        url = f"https://graph.facebook.com/v20.0/me/messages?access_token={FB_PAGE_TOKEN}"
        payload = {"recipient": {"id": sender_id}, "message": {"text": text}}
        if quick_replies:
            payload["message"]["quick_replies"] = [
                {"content_type": "text", "title": qr["title"], "payload": qr["payload"]} for qr in quick_replies
            ]
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(url, json=payload, headers=headers)
            logger.info("Meta API Response: %s", response.json())
        except requests.exceptions.RequestException as e:
            logger.error("Failed to send Meta message: %s", str(e))

# === Main Execution ===
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
