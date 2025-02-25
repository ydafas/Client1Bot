import os
import json
import logging
import gspread
import requests
from flask import Flask, request, jsonify
from oauth2client.service_account import ServiceAccountCredentials

# ✅ Flask App Setup
app = Flask(__name__)

# ✅ Logging Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ Load Google Sheets Credentials
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "service_account.json")

def authenticate_google_sheets():
    """Authenticate Google Sheets API."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(creds)
    return client

client = authenticate_google_sheets()
LEAD_SHEET = client.open("BotData").worksheet("Leads")  # Name of your Google Sheet
ORDER_SHEET = client.open("BotData").worksheet("Orders")

# ✅ Set Your Bot Credentials
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "secure_token")

# ✅ Webhook for Facebook Messenger
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
        logger.info("🔹 Received Meta Webhook Data: %s", data)

        if 'entry' in data:
            for entry in data['entry']:
                if 'messaging' in entry:
                    for messaging_event in entry['messaging']:
                        sender_id = messaging_event['sender']['id']
                        if 'message' in messaging_event:
                            message_text = messaging_event['message'].get('text', '').lower()
                            process_message(sender_id, message_text)
                        elif 'postback' in messaging_event:
                            payload = messaging_event['postback'].get('payload', '').lower()
                            process_message(sender_id, payload)

        return "EVENT_RECEIVED", 200

# ✅ Process Incoming Messages
def process_message(sender_id, message):
    if message in ['hi', 'hello', 'start']:
        send_message(sender_id, "Hey there! Welcome to TwoStep Automations! 🚀 How can I help?",
                     quick_replies=[{"title": "Services", "payload": "services"},
                                    {"title": "FAQs", "payload": "faq"},
                                    {"title": "Support", "payload": "support"},
                                    {"title": "Sales", "payload": "sales"},
                                    {"title": "Contact Us", "payload": "contact"}])
    elif message == 'services':
        send_message(sender_id, "We offer automated chatbots for businesses. How can we assist you?",
                     quick_replies=[{"title": "Learn More", "payload": "learn_more"},
                                    {"title": "Back to Main Menu", "payload": "start"}])
    elif message == 'faq':
        send_message(sender_id, "Here are some FAQs:\n1️⃣ What services do you offer?\n2️⃣ How much does it cost?\n3️⃣ Shipping info?",
                     quick_replies=[{"title": "Pricing", "payload": "pricing"},
                                    {"title": "Shipping", "payload": "shipping"},
                                    {"title": "Returns", "payload": "returns"},
                                    {"title": "Back to Main Menu", "payload": "start"}])
    elif message == 'support':
        send_message(sender_id, "Let’s solve your issue! What’s the problem?",
                     quick_replies=[{"title": "Order Issue", "payload": "order_issue"},
                                    {"title": "Technical Issue", "payload": "tech_issue"},
                                    {"title": "Back to Main Menu", "payload": "start"}])
    elif message == 'order_issue':
        send_message(sender_id, "Please enter your order number:")
        user_data[sender_id] = {"state": "waiting_order"}
    elif sender_id in user_data and user_data[sender_id]["state"] == "waiting_order":
        order_number = message
        save_order_to_sheets(sender_id, order_number)
        send_message(sender_id, "Your issue has been logged. A team member will follow up soon!",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])
        del user_data[sender_id]  # Clear user data after logging
    elif message == 'sales':
        send_message(sender_id, "Looking to shop? What interests you?",
                     quick_replies=[{"title": "Latest Offers", "payload": "offers"},
                                    {"title": "Products", "payload": "products"},
                                    {"title": "Lead Capture", "payload": "lead"},
                                    {"title": "Back to Main Menu", "payload": "start"}])
    elif message == 'lead':
        send_message(sender_id, "Enter your details:\n1. Name\n2. Email\n3. Phone (optional)")
        user_data[sender_id] = {"state": "waiting_lead"}
    elif sender_id in user_data and user_data[sender_id]["state"] == "waiting_lead":
        lead_data = message.split("\n")
        save_lead_to_sheets(sender_id, lead_data)
        send_message(sender_id, "Thanks for your info! We’ll reach out soon.",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])
        del user_data[sender_id]  # Clear user data after logging
    else:
        send_message(sender_id, "Sorry, I didn’t understand that. Try selecting an option or type 'start'.",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])

# ✅ Send Message to Messenger
def send_message(sender_id, text, quick_replies=None):
    if not FB_PAGE_TOKEN:
        logger.warning("FB_PAGE_TOKEN not set. Skipping Meta message.")
        return

    url = f"https://graph.facebook.com/v20.0/me/messages?access_token={FB_PAGE_TOKEN}"
    payload = {"recipient": {"id": sender_id}, "message": {"text": text}}

    if quick_replies:
        payload["message"]["quick_replies"] = [{"content_type": "text", "title": qr["title"], "payload": qr["payload"]} for qr in quick_replies]

    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers)
    logger.info("🔹 Meta API Response: %s", response.json())

# ✅ Save Order to Google Sheets
def save_order_to_sheets(sender_id, order_number):
    ORDER_SHEET.append_row([sender_id, order_number])
    logger.info(f"✅ Order logged: {sender_id} - {order_number}")

# ✅ Save Lead to Google Sheets
def save_lead_to_sheets(sender_id, lead_data):
    LEAD_SHEET.append_row([sender_id] + lead_data)
    logger.info(f"✅ Lead captured: {sender_id} - {lead_data}")

# ✅ Run Flask App
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
#