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
WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID", "")
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET", "")

BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Client1 Inc")
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@automatedbusiness.com")
SUPPORT_PHONE = os.environ.get("SUPPORT_PHONE", "(123) 456-7890")
BASE_PRICE = os.environ.get("BASE_PRICE", "$199")
SHIPPING_DAYS = os.environ.get("SHIPPING_DAYS", "3-5")
FREE_SHIPPING_THRESHOLD = os.environ.get("FREE_SHIPPING_THRESHOLD", "$50")
RETURN_POLICY_DAYS = os.environ.get("RETURN_POLICY_DAYS", "30")
PROMO_CODE = os.environ.get("PROMO_CODE", "CHAT20")
PRODUCT_CATALOG_LINK = os.environ.get("PRODUCT_CATALOG_LINK", "https://automatedbusiness.com/products")

user_data = {}

INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://localhost:10001")
SCHEDULING_URL = os.environ.get("SCHEDULING_URL", "http://localhost:10002")

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

# === New Meta Pages API Functions ===
def get_pages_list():
    """Retrieve list of pages accessible by the page token"""
    if not FB_PAGE_TOKEN:
        return None
    url = f"https://graph.facebook.com/v20.0/me/accounts?access_token={FB_PAGE_TOKEN}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get('data', [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch pages list: {str(e)}")
        return None

def get_page_metadata(page_id):
    """Retrieve metadata for a specific page"""
    if not FB_PAGE_TOKEN:
        return None
    url = f"https://graph.facebook.com/v20.0/{page_id}?fields=name,category,about&access_token={FB_PAGE_TOKEN}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch page metadata: {str(e)}")
        return None

def send_page_message(page_id, recipient_id, message):
    """Demonstrate pages_messaging by sending a message from a specific page"""
    if not FB_PAGE_TOKEN:
        return None
    url = f"https://graph.facebook.com/v20.0/{page_id}/messages?access_token={FB_PAGE_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message}
    }
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send page message: {str(e)}")
        return None

def get_business_info(page_id):
    """Demonstrate business_management by fetching business info"""
    if not FB_PAGE_TOKEN:
        return None
    url = f"https://graph.facebook.com/v20.0/{page_id}?fields=business&access_token={FB_PAGE_TOKEN}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch business info: {str(e)}")
        return None

def get_page_engagement(page_id):
    """Demonstrate pages_read_engagement by fetching recent post engagement"""
    if not FB_PAGE_TOKEN:
        return None
    url = f"https://graph.facebook.com/v20.0/{page_id}/feed?fields=reactions.summary(total_count),comments.summary(total_count)&limit=1&access_token={FB_PAGE_TOKEN}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get('data', [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch page engagement: {str(e)}")
        return None

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

# === Message Processing ===
def process_message(sender_id, message, platform="meta"):
    if message in ['start', 'get_started', 'welcome_message', 'back to main menu']:
        if sender_id in user_data:
            del user_data[sender_id]

    if message in ['hi', 'hello', 'start', 'get_started', 'welcome_message']:
        send_message(sender_id, f"Hey there! Welcome to {BUSINESS_NAME}! How can I help?",
                    quick_replies=[{"title": "Services", "payload": "services"},
                                   {"title": "FAQs", "payload": "faq"},
                                   {"title": "Support", "payload": "support"},
                                   {"title": "Sales", "payload": "sales"},
                                   {"title": "Contact Us", "payload": "contact"},
                                   {"title": "Page Info", "payload": "page_info"}],
                    platform=platform)
    elif message == 'page_info':
        pages = get_pages_list()
        if pages:
            page_list = "\n".join([f"- {page['name']} (ID: {page['id']})" for page in pages])
            send_message(sender_id,
                        f"Available Pages:\n{page_list}\n\nCommands:\n- 'metadata <page_id>'\n- 'message <page_id>'\n- 'business <page_id>'\n- 'engagement <page_id>'",
                        quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                        platform=platform)
        else:
            send_message(sender_id,
                        "Couldn't fetch page list. Please try again later.",
                        quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                        platform=platform)
    elif message.startswith('metadata '):
        page_id = message.split('metadata ')[1].strip()
        metadata = get_page_metadata(page_id)
        if metadata:
            response = f"Page Info:\nName: {metadata.get('name', 'N/A')}\nCategory: {metadata.get('category', 'N/A')}\nAbout: {metadata.get('about', 'N/A')}"
            send_message(sender_id,
                        response,
                        quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                        platform=platform)
        else:
            send_message(sender_id,
                        "Couldn't fetch page metadata. Make sure the page ID is correct.",
                        quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                        platform=platform)
    elif message.startswith('message '):
        page_id = message.split('message ')[1].strip()
        result = send_page_message(page_id, sender_id, "This is a test message from the page!")
        if result:
            send_message(sender_id,
                        f"Successfully sent a test message from page {page_id}!",
                        quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                        platform=platform)
        else:
            send_message(sender_id,
                        "Failed to send message. Check page ID and permissions.",
                        quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                        platform=platform)
    elif message.startswith('business '):
        page_id = message.split('business ')[1].strip()
        business_info = get_business_info(page_id)
        if business_info and 'business' in business_info:
            business = business_info['business']
            response = f"Business Info:\nName: {business.get('name', 'N/A')}\nID: {business.get('id', 'N/A')}"
            send_message(sender_id,
                        response,
                        quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                        platform=platform)
        else:
            send_message(sender_id,
                        "No business info found or error occurred.",
                        quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                        platform=platform)
    elif message.startswith('engagement '):
        page_id = message.split('engagement ')[1].strip()
        engagement_data = get_page_engagement(page_id)
        if engagement_data and len(engagement_data) > 0:
            post = engagement_data[0]
            reactions = post.get('reactions', {}).get('summary', {}).get('total_count', 0)
            comments = post.get('comments', {}).get('summary', {}).get('total_count', 0)
            response = f"Latest Post Engagement:\nReactions: {reactions}\nComments: {comments}"
            send_message(sender_id,
                        response,
                        quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                        platform=platform)
        else:
            send_message(sender_id,
                        "Couldn't fetch engagement data. No posts or permission issue.",
                        quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                        platform=platform)
    # ... (rest of your existing process_message function remains unchanged) ...
    elif message in ['services', 'service']:
        send_message(sender_id, f"We offer automated chatbots for businesses! How can we assist you?",
                    quick_replies=[{"title": "Learn More", "payload": "learn_more"},
                                   {"title": "Back to Main Menu", "payload": "start"}],
                    platform=platform)
    # ... (keeping all other existing conditions) ...
    else:
        send_message(sender_id, "Sorry, I didn’t understand that. Try selecting an option or type 'start'.",
                    quick_replies=[{"title": "Services", "payload": "services"},
                                   {"title": "FAQs", "payload": "faq"},
                                   {"title": "Support", "payload": "support"},
                                   {"title": "Sales", "payload": "sales"},
                                   {"title": "Contact Us", "payload": "contact"},
                                   {"title": "Page Info", "payload": "page_info"}],
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
    # ... (rest of send_message function remains unchanged) ...

# === Main Execution ===
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=True)