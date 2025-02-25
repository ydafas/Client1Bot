from flask import Flask, request, jsonify
import requests
import os
import json
import tempfile
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# 🔹 Set up logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔹 Load Google Credentials from Environment Variables (SECURE)
google_creds = os.getenv("GOOGLE_CREDENTIALS")
if google_creds:
    creds_dict = json.loads(google_creds)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_file:
        temp_file.write(json.dumps(creds_dict).encode())
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_file.name
else:
    raise Exception("GOOGLE_CREDENTIALS environment variable is missing")

# 🔹 Authenticate Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name(os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scope)
gc = gspread.authorize(credentials)

# 🔹 Google Sheet Configuration (Replace with your actual sheet ID)
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "your_google_sheet_id_here")
sheet = gc.open_by_key(SHEET_ID).sheet1  # Select the first sheet

# 🔹 Facebook API Credentials
FB_PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "secure_token")

# 🔹 Business Info
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Client1 Inc")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@client1.com")
SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "(123) 456-7890")
PRODUCT_CATALOG_LINK = os.getenv("PRODUCT_CATALOG_LINK", "https://client1.com/products")

# 🔹 User Data Storage (Temporary - Stored in Memory)
user_data = {}


# ✅ Webhook for Facebook Messenger
@app.route('/webhook', methods=['GET', 'POST'])
def fb_webhook():
    if request.method == 'GET':  # Verify Webhook
        verify_token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if verify_token == VERIFY_TOKEN:
            return challenge
        return "Verification failed", 403

    elif request.method == 'POST':  # Handle messages
        data = request.json
        logger.info("🔹 Received Meta Webhook Data: %s", data)

        if 'entry' in data:
            for entry in data['entry']:
                if 'messaging' in entry:
                    for messaging_event in entry['messaging']:
                        sender_id = messaging_event['sender']['id']
                        if 'message' in messaging_event:
                            if 'quick_reply' in messaging_event['message']:
                                payload = messaging_event['message']['quick_reply'].get('payload', '').lower().strip()
                                process_message(sender_id, payload)
                            else:
                                message_text = messaging_event['message'].get('text', '').lower().strip()
                                process_message(sender_id, message_text)
                        elif 'postback' in messaging_event:
                            payload = messaging_event['postback'].get('payload', '').lower().strip()
                            process_message(sender_id, payload)

        return "EVENT_RECEIVED", 200


# ✅ Process Incoming Messages
def process_message(sender_id, message):
    if message in ['start', 'get_started', 'welcome_message', 'back to main menu']:
        if sender_id in user_data:
            del user_data[sender_id]

    if message in ['hi', 'hello', 'start', 'get_started']:
        send_message(sender_id, f"Hey there! Welcome to {BUSINESS_NAME}! 🚀 How can I help?",
                     quick_replies=[{"title": "Services", "payload": "services"},
                                    {"title": "FAQs", "payload": "faq"},
                                    {"title": "Support", "payload": "support"},
                                    {"title": "Sales", "payload": "sales"},
                                    {"title": "Contact Us", "payload": "contact"}])

    elif message == 'support':
        send_message(sender_id, "Let’s solve your issue! What’s the problem?",
                     quick_replies=[{"title": "Order Issue", "payload": "order_issue"},
                                    {"title": "Technical Issue", "payload": "tech_issue"},
                                    {"title": "Back to Main Menu", "payload": "start"}])

    elif message == 'order_issue':
        send_message(sender_id, "Please provide your order number.")
        user_data[sender_id] = {"state": "waiting_order"}

    elif sender_id in user_data and user_data[sender_id].get("state") == "waiting_order":
        user_data[sender_id]["order_number"] = message
        send_message(sender_id, "How urgent is this?",
                     quick_replies=[{"title": "Urgent", "payload": "urgent"},
                                    {"title": "Not Urgent", "payload": "not_urgent"}])
        user_data[sender_id]["state"] = "waiting_urgency"

    elif sender_id in user_data and user_data[sender_id].get("state") == "waiting_urgency":
        user_data[sender_id]["urgency"] = message
        order_data = user_data.pop(sender_id)
        log_to_google_sheets(sender_id, order_data)
        send_message(sender_id, "A team member will follow up soon on your order.")

    elif message == 'sales':
        send_message(sender_id, "Interested in our products? What can I help with?",
                     quick_replies=[{"title": "Products", "payload": "products"},
                                    {"title": "Offers", "payload": "offers"},
                                    {"title": "Back to Main Menu", "payload": "start"}])

    elif message == 'products':
        send_message(sender_id, f"Check our products: {PRODUCT_CATALOG_LINK}",
                     quick_replies=[{"title": "Back to Sales", "payload": "sales"},
                                    {"title": "Back to Main Menu", "payload": "start"}])

    elif message == 'offers':
        send_message(sender_id, "Get 20% off with code CHAT20!",
                     quick_replies=[{"title": "Back to Sales", "payload": "sales"},
                                    {"title": "Back to Main Menu", "payload": "start"}])


# ✅ Log Data to Google Sheets
def log_to_google_sheets(sender_id, data):
    try:
        sheet.append_row([sender_id, data.get("order_number", ""), data.get("urgency", ""), "Pending"])
        logger.info("🔹 Successfully logged data to Google Sheets")
    except Exception as e:
        logger.error("🔹 Failed to log data to Google Sheets: %s", str(e))


# ✅ Send Messages
def send_message(sender_id, text, quick_replies=None):
    if not FB_PAGE_TOKEN:
        logger.warning("FB_PAGE_TOKEN not set. Skipping message.")
        return

    url = f"https://graph.facebook.com/v20.0/me/messages?access_token={FB_PAGE_TOKEN}"
    payload = {"recipient": {"id": sender_id}, "message": {"text": text}}

    if quick_replies:
        payload["message"]["quick_replies"] = [{"content_type": "text", "title": qr["title"], "payload": qr["payload"]}
                                               for qr in quick_replies]

    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers)
    logger.info("🔹 Meta API Response: %s", response.json())


# ✅ Run Flask Server
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
#