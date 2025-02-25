from flask import Flask, request, jsonify
import requests
import os
import logging
import json
import datetime
from oauth2client.service_account import ServiceAccountCredentials
from gspread import authorize

app = Flask(__name__)

# 🔹 Set up logging for Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔹 Set your credentials
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "secure_token")

# 🔹 Business Information
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Client1 Inc")
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@automatedbusiness.com")
SUPPORT_PHONE = os.environ.get("SUPPORT_PHONE", "(123) 456-7890")

# 🔹 Google Sheets Configuration
SPREADSHEET_ID = os.environ.get("GOOGLE_SPREADSHEET_ID", "1PPK-cYGb75IH9uKaUf4IACtpAnINwK-n_TAxj86BRlY")

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
    return creds

# Initialize Google Sheets
try:
    gc = authorize(authenticate_google_sheets())
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        support_sheet = sh.worksheet("Support Issues")
    except:
        support_sheet = sh.add_worksheet(title="Support Issues", rows="100", cols="10")
        support_sheet.append_row([
            "Sender ID", "Category", "User Name", "Order Number", "Urgency",
            "Website", "Issue Description", "Email", "Phone", "Company", "Timestamp"
        ])
except Exception as e:
    logger.error("Failed to initialize Google Sheets: %s", str(e))
    gc = None

user_data = {}

# ✅ Webhook Route
@app.route('/webhook', methods=['GET', 'POST'])
def fb_webhook():
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Verification failed", 403

    elif request.method == 'POST':
        data = request.json
        logger.info("🔹 Received Meta Webhook Data: %s", data)

        if 'entry' in data:
            for entry in data['entry']:
                if 'messaging' in entry:
                    for messaging_event in entry['messaging']:
                        sender_id = messaging_event['sender']['id']
                        if 'message' in messaging_event:
                            message_text = messaging_event['message'].get('text', '').strip().lower()
                            process_message(sender_id, message_text)
        return "EVENT_RECEIVED", 200

def process_message(sender_id, message):
    if message in ['start', 'get_started', 'back to main menu']:
        if sender_id in user_data:
            del user_data[sender_id]
        send_message(sender_id, f"Welcome to {BUSINESS_NAME}! How can I help?",
                     quick_replies=[{"title": "Support", "payload": "support"},
                                    {"title": "Sales", "payload": "sales"},
                                    {"title": "Contact", "payload": "contact"}])

    elif message == 'support':
        send_message(sender_id, "What kind of issue are you experiencing?",
                     quick_replies=[{"title": "Order Issue", "payload": "order_issue"},
                                    {"title": "Technical Issue", "payload": "tech_issue"},
                                    {"title": "Back to Main Menu", "payload": "start"}])

    elif message == 'order_issue':
        user_data[sender_id] = {"state": "waiting_order", "category": "Order Issue"}
        send_message(sender_id, "Please provide your order number.")

    elif user_data.get(sender_id, {}).get("state") == "waiting_order":
        user_data[sender_id]["order_number"] = message
        send_message(sender_id, "Thanks! Please provide your name.")
        user_data[sender_id]["state"] = "waiting_order_name"

    elif user_data.get(sender_id, {}).get("state") == "waiting_order_name":
        user_data[sender_id]["user_name"] = message
        send_message(sender_id, "Thanks! How urgent is this? (Urgent/Not Urgent)",
                     quick_replies=[{"title": "Urgent", "payload": "urgent"},
                                    {"title": "Not Urgent", "payload": "not_urgent"}])
        user_data[sender_id]["state"] = "waiting_urgency"

    elif user_data.get(sender_id, {}).get("state") == "waiting_urgency":
        user_data[sender_id]["urgency"] = message
        log_data(sender_id)
        send_message(sender_id, "Your order issue has been recorded. A support member will follow up.",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])
        del user_data[sender_id]

    elif message == 'tech_issue':
        user_data[sender_id] = {"state": "waiting_issue", "category": "Technical Issue"}
        send_message(sender_id, "Please provide your name.")

    elif user_data.get(sender_id, {}).get("state") == "waiting_issue":
        user_data[sender_id]["user_name"] = message
        send_message(sender_id, "Which website is this issue related to?")
        user_data[sender_id]["state"] = "waiting_website"

    elif user_data.get(sender_id, {}).get("state") == "waiting_website":
        user_data[sender_id]["website"] = message
        send_message(sender_id, "Please describe the technical issue.")
        user_data[sender_id]["state"] = "waiting_issue_description"

    elif user_data.get(sender_id, {}).get("state") == "waiting_issue_description":
        user_data[sender_id]["issue_description"] = message
        log_data(sender_id)
        send_message(sender_id, "Your technical issue has been recorded. A support member will follow up.",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])
        del user_data[sender_id]

def log_data(sender_id):
    if gc and support_sheet:
        try:
            data = user_data[sender_id]
            row = [
                sender_id,
                data.get("category", ""),
                data.get("user_name", ""),
                data.get("order_number", ""),
                data.get("urgency", ""),
                data.get("website", ""),
                data.get("issue_description", ""),
                "",
                "",
                "",
                datetime.datetime.now().isoformat()
            ]
            support_sheet.append_row(row)
            logger.info("Data logged for sender_id: %s", sender_id)
        except Exception as e:
            logger.error("Failed to write data: %s", str(e))

def send_message(sender_id, text, quick_replies=None):
    if not FB_PAGE_TOKEN:
        logger.warning("FB_PAGE_TOKEN not set.")
        return

    url = f"https://graph.facebook.com/v20.0/me/messages?access_token={FB_PAGE_TOKEN}"
    payload = {"recipient": {"id": sender_id}, "message": {"text": text}}

    if quick_replies:
        payload["message"]["quick_replies"] = [{"content_type": "text", "title": qr["title"], "payload": qr["payload"]} for qr in quick_replies]

    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers)
        logger.info("🔹 Meta API Response: %s", response.json())
    except requests.exceptions.RequestException as e:
        logger.error("Failed to send message: %s", str(e))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)), debug=True)
