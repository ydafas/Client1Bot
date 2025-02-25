import os
import requests
import datetime
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, request, jsonify

# 🔹 Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ✅ Facebook API Credentials
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")  # Your Facebook Page Access Token
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "secure_token")  # Verification token

# ✅ Google Sheets API Setup
SHEET_ID = os.environ.get("SHEET_ID", "")  # Google Sheet ID
SERVICE_ACCOUNT_FILE = "service_account.json"  # JSON Key file

def authenticate_google_sheets():
    """Authenticate Google Sheets API."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(creds)
    return client

client = authenticate_google_sheets()
sheet = client.open_by_key(SHEET_ID).sheet1  # Use the first sheet

def log_to_google_sheets(entry):
    """Log chatbot interactions to Google Sheets."""
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = [timestamp] + list(entry.values())  # Append timestamp before data
        sheet.append_row(row)
        logger.info("✅ Data logged to Google Sheets successfully!")
    except Exception as e:
        logger.error(f"❌ Error logging to Google Sheets: {e}")

# ✅ Webhook for Facebook Messenger
@app.route('/webhook', methods=['GET', 'POST'])
def fb_webhook():
    if request.method == 'GET':  # Webhook verification
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
user_data = {}

def process_message(sender_id, message):
    if message in ['hi', 'hello', 'start', 'get_started']:
        send_message(sender_id, "Hey there! Welcome to our chatbot! 🚀 How can I help?",
                     quick_replies=[{"title": "Services", "payload": "services"},
                                    {"title": "Support", "payload": "support"},
                                    {"title": "Sales", "payload": "sales"},
                                    {"title": "Contact", "payload": "contact"}])

    elif message == 'services':
        send_message(sender_id, "We offer automated chatbots for businesses! How can we assist you?",
                     quick_replies=[{"title": "Learn More", "payload": "learn_more"},
                                    {"title": "Back to Main Menu", "payload": "start"}])

    elif message == 'learn_more':
        send_message(sender_id, "Our chatbot solutions help automate customer interactions. Contact us for a demo!",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])

    elif message == 'support':
        send_message(sender_id, "Let’s solve your issue! What’s the problem?",
                     quick_replies=[{"title": "Order Issue", "payload": "order_issue"},
                                    {"title": "Technical Issue", "payload": "tech_issue"},
                                    {"title": "Back to Main Menu", "payload": "start"}])

    elif message == 'order_issue':
        send_message(sender_id, "Please provide your Order Number.")
        user_data[sender_id] = {"state": "waiting_order"}

    elif sender_id in user_data and user_data[sender_id]["state"] == "waiting_order":
        order_number = message
        send_message(sender_id, "How urgent is this? (Urgent/Not Urgent)",
                     quick_replies=[{"title": "Urgent", "payload": "urgent"},
                                    {"title": "Not Urgent", "payload": "not_urgent"}])
        user_data[sender_id]["order_number"] = order_number
        user_data[sender_id]["state"] = "waiting_urgency"

    elif sender_id in user_data and user_data[sender_id]["state"] == "waiting_urgency":
        urgency = message
        issue_data = {
            "Name": "N/A",
            "Email": "N/A",
            "Phone": "N/A",
            "Issue Type": "Order Issue",
            "Issue Details": "N/A",
            "Order Number": user_data[sender_id]["order_number"],
            "Urgency": urgency,
            "Message": "Issue Logged"
        }
        log_to_google_sheets(issue_data)
        send_message(sender_id, "✅ Your order issue has been recorded! A team member will follow up shortly.",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])
        del user_data[sender_id]

    elif message == 'sales':
        send_message(sender_id, "Interested in our products? What can I help with?",
                     quick_replies=[{"title": "Products", "payload": "products"},
                                    {"title": "Offers", "payload": "offers"},
                                    {"title": "Back to Main Menu", "payload": "start"}])

    elif message == 'products':
        send_message(sender_id, "Check out our product catalog here: https://yourstore.com/products",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])

    elif message == 'offers':
        send_message(sender_id, "We have an ongoing 20% discount! Use code CHAT20.",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])

    elif message == 'contact':
        send_message(sender_id, "📧 Email: support@yourbusiness.com\n📞 Phone: (123) 456-7890",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])

    else:
        send_message(sender_id, "Sorry, I didn’t understand that. Try selecting an option or type 'start'.",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])

# ✅ Send Messages
def send_message(sender_id, text, quick_replies=None):
    url = f"https://graph.facebook.com/v20.0/me/messages?access_token={FB_PAGE_TOKEN}"
    payload = {"recipient": {"id": sender_id}, "message": {"text": text}}

    if quick_replies:
        payload["message"]["quick_replies"] = [{"content_type": "text", "title": qr["title"], "payload": qr["payload"]} for qr in quick_replies]

    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers)
    logger.info("🔹 Meta API Response: %s", response.json())

# ✅ Run Flask App
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
