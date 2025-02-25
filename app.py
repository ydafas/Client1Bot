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
# Credentials (Use environment variables or local defaults for testing)
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "secure_token")
WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID", "")
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET", "")

# Business Variables (Configurable via environment variables)
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Client1 Inc")
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@automatedbusiness.com")
SUPPORT_PHONE = os.environ.get("SUPPORT_PHONE", "(123) 456-7890")
BASE_PRICE = os.environ.get("BASE_PRICE", "$199")
SHIPPING_DAYS = os.environ.get("SHIPPING_DAYS", "3-5")
FREE_SHIPPING_THRESHOLD = os.environ.get("FREE_SHIPPING_THRESHOLD", "$50")
RETURN_POLICY_DAYS = os.environ.get("RETURN_POLICY_DAYS", "30")
PROMO_CODE = os.environ.get("PROMO_CODE", "CHAT20")
PRODUCT_CATALOG_LINK = os.environ.get("PRODUCT_CATALOG_LINK", "https://automatedbusiness.com/products")

# User Data Storage (In-memory; use a DB in production)
user_data = {}

# Service URLs (Update for deployment)
INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://localhost:10001")
SCHEDULING_URL = os.environ.get("SCHEDULING_URL", "http://localhost:10002")

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
# Meta Webhook (Facebook, Instagram, Threads)
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
                                process_message(sender_id, payload, platform="meta")
                            else:
                                message_text = messaging_event['message'].get('text', '').lower().strip()
                                logger.info("Processing message text: %s for sender_id: %s", message_text, sender_id)
                                process_message(sender_id, message_text, platform="meta")
                        elif 'postback' in messaging_event:
                            payload = messaging_event['postback'].get('payload', '').lower().strip()
                            logger.info("Processing postback payload: %s for sender_id: %s", payload, sender_id)
                            process_message(sender_id, payload, platform="meta")
        return "EVENT_RECEIVED", 200


# WeChat Webhook (Commented out but preserved for future use)
# @app.route('/wechat', methods=['POST'])
# def wechat_webhook():
#    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
#        logger.warning("WeChat credentials not set. Skipping WeChat message.")
#        return "WeChat not configured", 400
#
#    data = request.get_data(as_text=True)
#    sender_id = "wechat_user"  # Placeholder; parse from XML in production
#    message_text = data.lower().strip()
#    process_message(sender_id, message_text, platform="wechat")
#    return "<xml><ToUserName><![CDATA[user]]></ToUserName><FromUserName><![CDATA[bot]]></FromUserName><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[Message received!]]></Content></xml>"

# === Message Processing ===
def process_message(sender_id, message, platform="meta"):
    # Reset state for certain commands
    if message in ['start', 'get_started', 'welcome_message', 'back to main menu']:
        if sender_id in user_data:
            del user_data[sender_id]

    # Main Menu and Non-Stateful Responses
    if message in ['hi', 'hello', 'start', 'get_started', 'welcome_message']:
        send_message(sender_id, f"Hey there! Welcome to {BUSINESS_NAME}! How can I help?",
                     quick_replies=[{"title": "Services", "payload": "services"},
                                    {"title": "FAQs", "payload": "faq"},
                                    {"title": "Support", "payload": "support"},
                                    {"title": "Sales", "payload": "sales"},
                                    {"title": "Contact Us", "payload": "contact"}],
                     platform=platform)
    elif message in ['services', 'service']:
        send_message(sender_id, f"We offer automated chatbots for businesses! How can we assist you?",
                     quick_replies=[{"title": "Learn More", "payload": "learn_more"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['learn_more', 'learn more']:
        send_message(sender_id,
                     f"Learn more about our services: We provide 24/7 customer support, inventory management, and scheduling solutions for businesses like {BUSINESS_NAME}. Visit {PRODUCT_CATALOG_LINK} for details or contact us at {SUPPORT_EMAIL}!",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['faq', 'faqs']:
        send_message(sender_id,
                     f"Here are some FAQs:\n1. What services do you offer?\n2. How much does it cost?\n3. Shipping info?",
                     quick_replies=[{"title": "Services", "payload": "services_info"},
                                    {"title": "Cost", "payload": "cost"},
                                    {"title": "Shipping", "payload": "shipping"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['services_info', 'services', 'what services do you offer']:
        send_message(sender_id,
                     f"We offer automated chatbots for businesses, providing 24/7 customer support, inventory management, and scheduling solutions.",
                     quick_replies=[{"title": "Back to FAQs", "payload": "faq"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['cost', 'how much does it cost']:
        send_message(sender_id, f"Our chatbot setup starts at {BASE_PRICE}. Subscription plans available.",
                     quick_replies=[{"title": "Back to FAQs", "payload": "faq"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['shipping', 'ship', 'shipping info']:
        send_message(sender_id, f"Shipping takes {SHIPPING_DAYS} days. Free over {FREE_SHIPPING_THRESHOLD}!",
                     quick_replies=[{"title": "Back to FAQs", "payload": "faq"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['support', 'help']:
        send_message(sender_id, "Let’s solve your issue! What’s the problem?",
                     quick_replies=[{"title": "Order Issue", "payload": "order_issue"},
                                    {"title": "Technical Issue", "payload": "tech_issue"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['order_issue', 'order issue']:
        send_message(sender_id, "Please provide your order number.", platform=platform)
        user_data[sender_id] = {"state": "order_number", "category": "Order Issue", "data": {}}
    elif message in ['tech_issue', 'technical_issue', 'technical issues']:
        send_message(sender_id, "Please provide your name.", platform=platform)
        user_data[sender_id] = {"state": "tech_name", "category": "Technical Issue", "data": {}}
    elif message in ['contact', 'contact us']:
        send_message(sender_id, f"Email: {SUPPORT_EMAIL}\nPhone: {SUPPORT_PHONE}",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message == 'sales':
        send_message(sender_id, "Interested in our products? What can I help with?",
                     quick_replies=[{"title": "Products", "payload": "products"},
                                    {"title": "Offers", "payload": "offers"},
                                    {"title": "Lead Capture", "payload": "lead"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message == 'products':
        send_message(sender_id, f"Check our products: {PRODUCT_CATALOG_LINK}",
                     quick_replies=[{"title": "Back to Sales", "payload": "sales"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message == 'offers':
        send_message(sender_id, f"Get 20% off with code {PROMO_CODE}!",
                     quick_replies=[{"title": "Back to Sales", "payload": "sales"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message == 'lead':
        send_message(sender_id, "Please provide your name.", platform=platform)
        user_data[sender_id] = {"state": "lead_name", "category": "Lead Capture", "data": {}}
    elif message == 'inventory':
        send_message(sender_id, "Which product would you like to check? (e.g., chatbot_basic, chatbot_pro)",
                     quick_replies=[{"title": "Basic Chatbot", "payload": "check_basic"},
                                    {"title": "Pro Chatbot", "payload": "check_pro"},
                                    {"title": "Enterprise Chatbot", "payload": "check_enterprise"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['check_basic', 'check_pro', 'check_enterprise']:
        product_id = message.replace("check_", "")
        response = requests.get(f"{INVENTORY_URL}/inventory/{product_id}")
        if response.status_code == 200:
            data = response.json()
            availability = "in stock" if data["available"] else "out of stock"
            send_message(sender_id,
                         f"{data['product']}: {data['quantity']} available ({availability}), Price: {data['price']}",
                         quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                         platform=platform)
        else:
            send_message(sender_id, "Sorry, couldn’t check inventory. Try again later.",
                         quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                         platform=platform)
    elif message == 'schedule':
        send_message(sender_id, "When would you like to schedule a consultation? Enter a date (YYYY-MM-DD).",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
        user_data[sender_id] = {"state": "waiting_schedule_date", "schedule_date": None}
    elif message and sender_id in user_data and user_data[sender_id]["state"] == "waiting_schedule_date":
        date = message
        response = requests.get(f"{SCHEDULING_URL}/scheduling/available/{date}")
        if response.status_code == 200:
            slots = response.json()["available_slots"]
            if slots:
                send_message(sender_id, f"Available slots on {date}: {', '.join(slots)}. Pick a time (HH:MM).",
                             quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                             platform=platform)
                user_data[sender_id]["state"] = "waiting_schedule_time"
                user_data[sender_id]["schedule_date"] = date
            else:
                send_message(sender_id, "No slots available on that date. Try another.",
                             quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                             platform=platform)
                del user_data[sender_id]
        else:
            send_message(sender_id, "Invalid date or error. Use YYYY-MM-DD.",
                         quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                         platform=platform)
            del user_data[sender_id]
    elif message and sender_id in user_data and user_data[sender_id]["state"] == "waiting_schedule_time":
        time = message
        response = requests.post(f"{SCHEDULING_URL}/scheduling", json={
            "customer_id": sender_id,
            "date": user_data[sender_id]["schedule_date"],
            "time": time,
            "service": "Chatbot Consultation"
        })
        if response.status_code == 201:
            data = response.json()
            send_message(sender_id, f"Appointment booked for {data['details']['date']}. Anything else?",
                         quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                         platform=platform)
        else:
            send_message(sender_id, "Couldn’t book. Slot unavailable or invalid time. Try again.",
                         quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                         platform=platform)
        del user_data[sender_id]

    # Order Issue Flow
    elif sender_id in user_data and user_data[sender_id]["category"] == "Order Issue":
        state = user_data[sender_id]["state"]
        data = user_data[sender_id]["data"]
        if state == "order_number":
            data["order_number"] = message
            send_message(sender_id, "Your name?", platform=platform)
            user_data[sender_id]["state"] = "order_name"
        elif state == "order_name":
            data["name"] = message
            send_message(sender_id, "Your email address?", platform=platform)
            user_data[sender_id]["state"] = "order_email"
        elif state == "order_email":
            data["email"] = message
            send_message(sender_id, "Your phone number?", platform=platform)
            user_data[sender_id]["state"] = "order_phone"
        elif state == "order_phone":
            data["phone"] = message
            send_message(sender_id, "How urgent is this? (Urgent/Not Urgent)",
                         quick_replies=[{"title": "Urgent", "payload": "urgent"},
                                        {"title": "Not Urgent", "payload": "not_urgent"}],
                         platform=platform)
            user_data[sender_id]["state"] = "order_urgency"
        elif state == "order_urgency":
            data["urgency"] = message
            send_message(sender_id, "Your business name?", platform=platform)
            user_data[sender_id]["state"] = "order_business"
        elif state == "order_business":
            data["business_name"] = message
            send_message(sender_id, "Your website (if applicable)?", platform=platform)
            user_data[sender_id]["state"] = "order_website"
        elif state == "order_website":
            data["website"] = message
            write_to_google_sheet(sender_id, "Order Issue", data)
            send_message(sender_id, "Thanks! A team member will follow up soon.", platform=platform)
            del user_data[sender_id]

    # Technical Issue Flow
    elif sender_id in user_data and user_data[sender_id]["category"] == "Technical Issue":
        state = user_data[sender_id]["state"]
        data = user_data[sender_id]["data"]
        if state == "tech_name":
            data["name"] = message
            send_message(sender_id, "Your email address?", platform=platform)
            user_data[sender_id]["state"] = "tech_email"
        elif state == "tech_email":
            data["email"] = message
            send_message(sender_id, "Your phone number?", platform=platform)
            user_data[sender_id]["state"] = "tech_phone"
        elif state == "tech_phone":
            data["phone"] = message
            send_message(sender_id, "How urgent is this? (Urgent/Not Urgent)",
                         quick_replies=[{"title": "Urgent", "payload": "urgent"},
                                        {"title": "Not Urgent", "payload": "not_urgent"}],
                         platform=platform)
            user_data[sender_id]["state"] = "tech_urgency"
        elif state == "tech_urgency":
            data["urgency"] = message
            send_message(sender_id, "Your business name?", platform=platform)
            user_data[sender_id]["state"] = "tech_business"
        elif state == "tech_business":
            data["business_name"] = message
            send_message(sender_id, "Your website (if applicable)?", platform=platform)
            user_data[sender_id]["state"] = "tech_website"
        elif state == "tech_website":
            data["website"] = message
            send_message(sender_id, "Please describe your technical issue.", platform=platform)
            user_data[sender_id]["state"] = "tech_description"
        elif state == "tech_description":
            data["issue_description"] = message
            write_to_google_sheet(sender_id, "Technical Issue", data)
            send_message(sender_id, "Thanks! A team member will follow up soon.", platform=platform)
            del user_data[sender_id]

    # Lead Capture Flow
    elif sender_id in user_data and user_data[sender_id]["category"] == "Lead Capture":
        state = user_data[sender_id]["state"]
        data = user_data[sender_id]["data"]
        if state == "lead_name":
            data["name"] = message
            send_message(sender_id, "Your email address?", platform=platform)
            user_data[sender_id]["state"] = "lead_email"
        elif state == "lead_email":
            data["email"] = message
            send_message(sender_id, "Your phone number?", platform=platform)
            user_data[sender_id]["state"] = "lead_phone"
        elif state == "lead_phone":
            data["phone"] = message
            send_message(sender_id, "Your business name?", platform=platform)
            user_data[sender_id]["state"] = "lead_business"
        elif state == "lead_business":
            data["business_name"] = message
            send_message(sender_id, "Your website (if applicable)?", platform=platform)
            user_data[sender_id]["state"] = "lead_website"
        elif state == "lead_website":
            data["website"] = message
            write_to_google_sheet(sender_id, "Lead Capture", data)
            send_message(sender_id, "Thanks for your info. We’ll reach out soon.", platform=platform)
            del user_data[sender_id]

    # Fallback
    else:
        send_message(sender_id, "Sorry, I didn’t understand that. Try selecting an option or type 'start'.",
                     quick_replies=[{"title": "Services", "payload": "services"},
                                    {"title": "FAQs", "payload": "faq"},
                                    {"title": "Support", "payload": "support"},
                                    {"title": "Sales", "payload": "sales"},
                                    {"title": "Contact Us", "payload": "contact"}],
                     platform=platform)


# === Helper Functions ===
def write_to_google_sheet(sender_id, category, data):
    if gc and worksheet:
        try:
            row = [
                sender_id,
                category,
                data.get("name", ""),
                data.get("order_number", ""),
                data.get("urgency", ""),
                data.get("website", ""),
                data.get("issue_description", ""),
                data.get("email", ""),
                data.get("phone", ""),
                data.get("business_name", ""),
                datetime.datetime.now().isoformat()
            ]
            worksheet.append_row(row)
            logger.info("Data written to Google Sheet for sender_id: %s, category: %s", sender_id, category)
        except Exception as e:
            logger.error("Failed to write to Google Sheet: %s", str(e))


def send_message(sender_id, text, quick_replies=None, platform="meta"):
    if platform == "meta" and FB_PAGE_TOKEN:
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
    elif platform == "wechat" and WECHAT_APP_ID and WECHAT_APP_SECRET:
        url = f"https://api.wechat.com/cgi-bin/message/custom/send?access_token={get_wechat_access_token()}"
        payload = {
            "touser": sender_id,
            "msgtype": "text",
            "text": {"content": text}
        }
        if quick_replies:
            payload["msgtype"] = "news"
            payload["news"] = {"articles": [{"title": qr["title"], "url": "https://your.link"} for qr in quick_replies]}
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(url, json=payload, headers=headers)
            logger.info("WeChat API Response: %s", response.json())
        except requests.exceptions.RequestException as e:
            logger.error("Failed to send WeChat message: %s", str(e))


# WeChat Helper Function (Preserved for future use)
def get_wechat_access_token():
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        raise ValueError("WeChat credentials not set")
    url = f"https://api.wechat.com/cgi-bin/token?grant_type=client_credential&appid={WECHAT_APP_ID}&secret={WECHAT_APP_SECRET}"
    response = requests.get(url)
    return response.json()["access_token"]


# === Main Execution ===
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=True)