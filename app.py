from flask import Flask, request, jsonify
import requests
import os
import logging
import json
from oauth2client.service_account import ServiceAccountCredentials
from gspread import authorize, Worksheet
import datetime

app = Flask(__name__)

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "secure_token")
SPREADSHEET_ID = os.environ.get("1PPK-cYGb75IH9uKaUf4IACtpAnINwK-n_TAxj86BRlY", "")
SHEET_NAME = os.environ.get("Lead and Issue Tracker", "Support Issues")

# Authenticate Google Sheets
def authenticate_google_sheets():
    google_credentials_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not google_credentials_json:
        raise ValueError("GOOGLE_CREDENTIALS environment variable not set")
    credentials_dict = json.loads(google_credentials_json)
    scope = ['https://www.googleapis.com/auth/spreadsheets']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    return creds

gc = authorize(authenticate_google_sheets())
sh = gc.open_by_key(SPREADSHEET_ID)
worksheet = sh.worksheet(SHEET_NAME)

# Webhook Endpoint
@app.route('/webhook', methods=['GET', 'POST'])
def fb_webhook():
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Verification failed", 403
    elif request.method == 'POST':
        data = request.json
        logger.info("Received Webhook Data: %s", data)
        for entry in data.get('entry', []):
            for messaging_event in entry.get('messaging', []):
                sender_id = messaging_event['sender']['id']
                if 'message' in messaging_event:
                    if 'quick_reply' in messaging_event['message']:
                        process_message(sender_id, messaging_event['message']['quick_reply']['payload'].lower())
                    else:
                        process_message(sender_id, messaging_event['message']['text'].lower())
        return "EVENT_RECEIVED", 200

# Process Messages
def process_message(sender_id, message):
    if message == "support":
        send_message(sender_id, "What’s the problem?",
                     quick_replies=[{"title": "Order Issue", "payload": "order_issue"},
                                    {"title": "Technical Issue", "payload": "tech_issue"},
                                    {"title": "Back to Main Menu", "payload": "start"}])

    elif message == "order_issue":
        send_message(sender_id, "Please provide your order number.")
        user_data[sender_id] = {"state": "waiting_order_number"}

    elif sender_id in user_data and user_data[sender_id]["state"] == "waiting_order_number":
        user_data[sender_id]["order_number"] = message
        send_message(sender_id, "Got it! Please enter your full name.")
        user_data[sender_id]["state"] = "waiting_order_name"

    elif sender_id in user_data and user_data[sender_id]["state"] == "waiting_order_name":
        user_data[sender_id]["user_name"] = message
        send_message(sender_id, "How urgent is this? (Urgent/Not Urgent)",
                     quick_replies=[{"title": "Urgent", "payload": "urgent"},
                                    {"title": "Not Urgent", "payload": "not_urgent"}])
        user_data[sender_id]["state"] = "waiting_order_urgency"

    elif sender_id in user_data and user_data[sender_id]["state"] == "waiting_order_urgency":
        urgency = message
        order_number = user_data[sender_id].get("order_number", "N/A")
        user_name = user_data[sender_id].get("user_name", "N/A")
        worksheet.append_row([sender_id, "Order Issue", f"Order #{order_number}", user_name, urgency, "New", datetime.datetime.now().isoformat()])
        send_message(sender_id, f"Thanks {user_name}! A team member will follow up soon on your order issue ({urgency}).",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])
        del user_data[sender_id]

    elif message == "tech_issue":
        send_message(sender_id, "Please enter your full name.")
        user_data[sender_id] = {"state": "waiting_tech_name"}

    elif sender_id in user_data and user_data[sender_id]["state"] == "waiting_tech_name":
        user_data[sender_id]["user_name"] = message
        send_message(sender_id, "What website are you having issues with?")
        user_data[sender_id]["state"] = "waiting_tech_website"

    elif sender_id in user_data and user_data[sender_id]["state"] == "waiting_tech_website":
        user_data[sender_id]["website_name"] = message
        send_message(sender_id, "Describe your technical issue.")
        user_data[sender_id]["state"] = "waiting_tech_description"

    elif sender_id in user_data and user_data[sender_id]["state"] == "waiting_tech_description":
        issue_description = message
        user_name = user_data[sender_id].get("user_name", "N/A")
        website_name = user_data[sender_id].get("website_name", "N/A")
        worksheet.append_row([sender_id, "Technical Issue", f"Website: {website_name}", user_name, issue_description, "New", datetime.datetime.now().isoformat()])
        send_message(sender_id, f"Thanks {user_name}! A team member will follow up soon regarding your issue with {website_name}.",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}])
        del user_data[sender_id]

# Send Messages
def send_message(sender_id, text, quick_replies=None):
    payload = {"recipient": {"id": sender_id}, "message": {"text": text}}
    if quick_replies:
        payload["message"]["quick_replies"] = [{"content_type": "text", "title": qr["title"], "payload": qr["payload"]} for qr in quick_replies]
    requests.post(f"https://graph.facebook.com/v20.0/me/messages?access_token={FB_PAGE_TOKEN}", json=payload)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)), debug=True)
