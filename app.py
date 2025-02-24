from flask import Flask, request, jsonify
import requests
import os
import logging

app = Flask(__name__)

# 🔹 Set up logging for Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔹 Set your credentials (Use environment variables or local defaults for testing)
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")  # Use your generated token; empty for testing without Meta
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "secure_token")  # Default for testing
WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID", "")  # Leave empty if not using WeChat
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET", "")  # Leave empty if not using WeChat

# 🔹 Configurable Business Variables (Use environment variables or local defaults)
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Automated Business")
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@automatedbusiness.com")
SUPPORT_PHONE = os.environ.get("SUPPORT_PHONE", "(123) 456-7890")
BASE_PRICE = os.environ.get("BASE_PRICE", "$199")
SHIPPING_DAYS = os.environ.get("SHIPPING_DAYS", "3-5")
FREE_SHIPPING_THRESHOLD = os.environ.get("FREE_SHIPPING_THRESHOLD", "$50")
RETURN_POLICY_DAYS = os.environ.get("RETURN_POLICY_DAYS", "30")
PROMO_CODE = os.environ.get("PROMO_CODE", "CHAT20")
PRODUCT_CATALOG_LINK = os.environ.get("PRODUCT_CATALOG_LINK", "https://automatedbusiness.com/products")

# 🔹 User Data Storage (In-memory for simplicity; use a DB in production)
user_data = {}  # Dictionary to store user info (e.g., name, email, order)

# 🔹 Local Testing URLs (Update for Render deployment or client-specific instances)
INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://localhost:10001")  # Default for local testing
SCHEDULING_URL = os.environ.get("SCHEDULING_URL", "http://localhost:10002")  # Default for local testing

# ✅ Webhooks for Multiple Platforms (Meta: Facebook, Instagram, Threads)
@app.route('/webhook', methods=['GET', 'POST'])
def fb_webhook():
    if request.method == 'GET':  # Verification step
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
                        if 'message' in messaging_event:
                            sender_id = messaging_event['sender']['id']
                            message_text = messaging_event['message'].get('text', '').lower()
                            process_message(sender_id, message_text, platform="meta")
                        elif 'optin' in messaging_event:  # Handle messaging_optins for testing
                            sender_id = messaging_event['sender']['id']
                            logger.info("🔹 Received messaging_optins for sender_id: %s", sender_id)
                            if FB_PAGE_TOKEN:
                                send_message(sender_id, f"Welcome to {BUSINESS_NAME}! You’ve opted into messaging. How can I help?",
                                             quick_replies=[{"title": "Start", "payload": "start"}],
                                             platform="meta")
                        elif 'postback' in messaging_event:  # Handle postbacks (e.g., quick replies)
                            sender_id = messaging_event['sender']['id']
                            payload = messaging_event['postback'].get('payload', '').lower()
                            process_message(sender_id, payload, platform="meta")

        return "EVENT_RECEIVED", 200

# ✅ WeChat Webhook (Comment out if not needed)
@app.route('/wechat', methods=['POST'])
def wechat_webhook():
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        logger.warning("WeChat credentials not set. Skipping WeChat message.")
        return "WeChat not configured", 400

    data = request.get_data(as_text=True)  # WeChat sends XML, parse it if needed
    sender_id = "wechat_user"  # Placeholder; parse from XML
    message_text = data.lower()  # Simplify for demo; use XML parsing in production
    process_message(sender_id, message_text, platform="wechat")
    return "<xml><ToUserName><![CDATA[user]]></ToUserName><FromUserName><![CDATA[bot]]></FromUserName><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[Message received!]]></Content></xml>"

# ✅ Process Incoming Messages (Multi-Platform Compatible)
def process_message(sender_id, message, platform="meta"):
    # Ensure user_data exists for the sender
    if sender_id not in user_data:
        user_data[sender_id] = {"state": None}  # Initialize user data

    # Main menu options
    if message in ['hi', 'hello', 'start']:
        send_message(sender_id, f"Hey there! Welcome to {BUSINESS_NAME}! 🚀 How can I help?",
                     quick_replies=[{"title": "Services", "payload": "services"},
                                    {"title": "FAQs", "payload": "faq"},
                                    {"title": "Support", "payload": "support"},
                                    {"title": "Sales", "payload": "sales"},
                                    {"title": "Contact Us", "payload": "contact"}],
                     platform=platform)

    elif message == 'services':
        send_message(sender_id, f"We offer automated chatbots for businesses! How can we assist you?",
                     quick_replies=[{"title": "Learn More", "payload": "learn_more"},
                                    {"title": "Back to Menu", "payload": "start"}],
                     platform=platform)

    elif message == 'learn_more':
        send_message(sender_id, "Here’s more info about our chatbot services...",
                     quick_replies=[{"title": "Pricing", "payload": "pricing"},
                                    {"title": "Back", "payload": "services"}],
                     platform=platform)

    # Prevent KeyError by checking 'state' before accessing it
    if "state" in user_data[sender_id] and user_data[sender_id]["state"] == "waiting_schedule_date":
        date = message
        user_data[sender_id]["schedule_date"] = date
        send_message(sender_id, f"Got it! What time would you like on {date}?",
                     quick_replies=[{"title": "09:00 AM", "payload": "time_09"},
                                    {"title": "10:00 AM", "payload": "time_10"},
                                    {"title": "Back", "payload": "start"}],
                     platform=platform)
        user_data[sender_id]["state"] = "waiting_schedule_time"


# ✅ Send Messages (Multi-Platform Compatible)
def send_message(sender_id, text, quick_replies=None, platform="meta"):
    if platform == "meta":  # Facebook/Instagram/Threads
        if not FB_PAGE_TOKEN:
            logger.warning("FB_PAGE_TOKEN not set. Skipping Meta message.")
            return  # Skip sending if no token (for testing without Meta)
        url = f"https://graph.facebook.com/v20.0/me/messages?access_token={FB_PAGE_TOKEN}"  # Updated to v20.0 (current as of Feb 2025)
        payload = {
            "recipient": {"id": sender_id},
            "message": {"text": text}
        }

        if quick_replies:
            payload["message"]["quick_replies"] = [
                {"content_type": "text", "title": qr["title"], "payload": qr["payload"]} for qr in quick_replies
            ]

        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers)
        logger.info("🔹 Meta API Response: %s", response.json())
    elif platform == "wechat":  # WeChat
        if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
            logger.warning("WeChat credentials not set. Skipping WeChat message.")
            return  # Skip sending if no credentials
        url = f"https://api.wechat.com/cgi-bin/message/custom/send?access_token={get_wechat_access_token()}"
        payload = {
            "touser": sender_id,
            "msgtype": "text",
            "text": {"content": text}
        }
        if quick_replies:
            # WeChat doesn’t natively support quick replies; use buttons or menus
            payload["msgtype"] = "news"  # Example; adjust for buttons
            payload["news"] = {"articles": [{"title": qr["title"], "url": "https://your.link"} for qr in quick_replies]}
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers)
        logger.info("🔹 WeChat API Response: %s", response.json())

# ✅ Helper Function for WeChat
def get_wechat_access_token():
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        raise ValueError("WeChat credentials not set")
    url = f"https://api.wechat.com/cgi-bin/token?grant_type=client_credential&appid={WECHAT_APP_ID}&secret={WECHAT_APP_SECRET}"
    response = requests.get(url)
    return response.json()["access_token"]

# ✅ Run Flask Server for Local Testing or Render Deployment
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  # Default for local testing; Render overrides
    app.run(host='0.0.0.0', port=port, debug=True)