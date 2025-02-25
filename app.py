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
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Client1 Inc")
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
                            message_text = messaging_event['message'].get('text', '').lower().strip()
                            logger.info("🔹 Processing message text: %s for sender_id: %s", message_text, sender_id)
                            process_message(sender_id, message_text, platform="meta")
                        elif 'optin' in messaging_event:  # Handle messaging_optins for testing
                            sender_id = messaging_event['sender']['id']
                            logger.info("🔹 Received messaging_optins for sender_id: %s", sender_id)
                            if FB_PAGE_TOKEN and 'payload' in messaging_event['optin'] and messaging_event['optin']['payload'] != 'start':
                                # Only send subscription message for actual opt-in payloads, not 'start'
                                send_message(sender_id, f"Welcome to {BUSINESS_NAME}! You’ve opted into messaging. How can I help?",
                                             quick_replies=[{"title": "Get Started", "payload": "get_started"}],
                                             platform="meta")
                        elif 'postback' in messaging_event:  # Handle postbacks (e.g., quick replies, Get Started)
                            sender_id = messaging_event['sender']['id']
                            payload = messaging_event['postback'].get('payload', '').lower().strip()
                            logger.info("🔹 Processing postback payload: %s for sender_id: %s", payload, sender_id)
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
    message_text = data.lower().strip()  # Simplify for demo; use XML parsing in production
    process_message(sender_id, message_text, platform="wechat")
    return "<xml><ToUserName><![CDATA[user]]></ToUserName><FromUserName><![CDATA[bot]]></FromUserName><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[Message received!]]></Content></xml>"

# ✅ Process Incoming Messages (Multi-Platform Compatible)
def process_message(sender_id, message, platform="meta"):
    # Clear state if processing a reset command to prevent interference
    if message in ['start', 'get_started', 'back to main menu']:
        if sender_id in user_data:
            del user_data[sender_id]  # Reset state for new interactions

    # Handle non-stateful messages (quick replies, standalone commands) first
    if message in ['hi', 'hello', 'start', 'get_started', 'back to main menu']:  # Handle Get Started button and text input
        send_message(sender_id, f"Hey there! Welcome to {BUSINESS_NAME}! 🚀 How can I help?",
                     quick_replies=[{"title": "Services", "payload": "services"},
                                    {"title": "FAQs", "payload": "faq"},
                                    {"title": "Support", "payload": "support"},
                                    {"title": "Sales", "payload": "sales"},
                                    {"title": "Contact Us", "payload": "contact"}],
                     platform=platform)
    elif message in ['services', 'service']:  # Handle variations in case or text
        send_message(sender_id, f"We offer automated chatbots for businesses! How can we assist you?",
                     quick_replies=[{"title": "Learn More", "payload": "learn_more"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['learn_more', 'learn more']:  # Handle both payload and text input
        send_message(sender_id, f"Learn more about our services: We provide 24/7 customer support, inventory management, and scheduling solutions for businesses like {BUSINESS_NAME}. Visit {PRODUCT_CATALOG_LINK} for details or contact us at {SUPPORT_EMAIL}!",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['faq', 'faqs']:  # Handle variations in case or text
        send_message(sender_id, f"Here are some FAQs:\n1. What services do you offer?\n2. How much does it cost?\n3. Shipping info?",
                     quick_replies=[{"title": "Services", "payload": "services_info"},
                                    {"title": "Cost", "payload": "cost"},
                                    {"title": "Shipping", "payload": "shipping"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['services_info', 'services', 'what services do you offer']:  # Handle FAQ option 1
        send_message(sender_id, f"We offer automated chatbots for businesses, providing 24/7 customer support, inventory management, and scheduling solutions.",
                     quick_replies=[{"title": "Back to FAQs", "payload": "faq"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['cost', 'how much does it cost']:  # Handle FAQ option 2
        send_message(sender_id, f"Our chatbot setup starts at {BASE_PRICE}. Subscription plans available.",
                     quick_replies=[{"title": "Back to FAQs", "payload": "faq"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['shipping', 'ship', 'shipping info']:  # Handle FAQ option 3
        send_message(sender_id, f"Shipping takes {SHIPPING_DAYS} days. Free over {FREE_SHIPPING_THRESHOLD}!",
                     quick_replies=[{"title": "Back to FAQs", "payload": "faq"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['support', 'help']:  # Handle variations
        send_message(sender_id, "Let’s solve your issue! What’s the problem?",
                     quick_replies=[{"title": "Order Issue", "payload": "order_issue"},
                                    {"title": "Technical Issue", "payload": "tech_issue"},
                                    {"title": "Other", "payload": "other_issue"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message in ['order_issue', 'order issue']:  # Handle variations for Order Issue
        send_message(sender_id, "Please provide your order number.",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
        user_data[sender_id] = {"state": "waiting_order"}
    elif message in ['tech_issue', 'technical_issue', 'other_issue']:  # Handle variations
        send_message(sender_id, "Describe your issue briefly.",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
        user_data[sender_id] = {"state": "waiting_issue"}
    elif message == 'sales':
        send_message(sender_id, "Interested in our products? What can I help with?",
                     quick_replies=[{"title": "Products", "payload": "products"},
                                    {"title": "Offers", "payload": "offers"},
                                    {"title": "Lead Capture", "payload": "lead"},
                                    {"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message == 'contact':
        send_message(sender_id, f"📧 Email: {SUPPORT_EMAIL}\n📞 Phone: {SUPPORT_PHONE}",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message == 'products':
        send_message(sender_id, f"Check our products: {PRODUCT_CATALOG_LINK}",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message == 'offers':
        send_message(sender_id, f"Get 20% off with code {PROMO_CODE}!",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
    elif message == 'lead':
        send_message(sender_id, "Interested in our services? Provide your info:\n1. Name\n2. Email\n3. Phone (optional)\n4. Company (optional)",
                     quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                     platform=platform)
        user_data[sender_id] = {"state": "waiting_lead", "lead_data": {}}
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
            send_message(sender_id, f"{data['product']}: {data['quantity']} available ({availability}), Price: {data['price']}",
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
                del user_data[sender_id]  # Clear user data if no slots available
        else:
            send_message(sender_id, "Invalid date or error. Use YYYY-MM-DD.",
                         quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                         platform=platform)
            del user_data[sender_id]  # Clear user data on error
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
        del user_data[sender_id]  # Clear user data after booking
    elif message in ['cancel_schedule', 'cancel']:  # Handle variations
        response = requests.delete(f"{SCHEDULING_URL}/scheduling/{sender_id}")
        if response.status_code == 200:
            send_message(sender_id, "Appointment canceled. Anything else?",
                         quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                         platform=platform)
        else:
            send_message(sender_id, "No appointment found to cancel. Try again.",
                         quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                         platform=platform)
        if sender_id in user_data:
            del user_data[sender_id]  # Clear user data after cancellation
    else:
        if sender_id in user_data:
            if user_data[sender_id]["state"] == "waiting_order":
                user_data[sender_id]["order_number"] = message
                send_message(sender_id, "Thanks! How urgent is this? (Urgent/Not Urgent)",
                             quick_replies=[{"title": "Urgent", "payload": "urgent"},
                                            {"title": "Not Urgent", "payload": "not_urgent"},
                                            {"title": "Back to Main Menu", "payload": "start"}],
                             platform=platform)
                user_data[sender_id]["state"] = "waiting_urgency"
            elif user_data[sender_id]["state"] == "waiting_issue":
                user_data[sender_id]["issue"] = message
                send_message(sender_id, "Thanks! How urgent is this? (Urgent/Not Urgent)",
                             quick_replies=[{"title": "Urgent", "payload": "urgent"},
                                            {"title": "Not Urgent", "payload": "not_urgent"},
                                            {"title": "Back to Main Menu", "payload": "start"}],
                             platform=platform)
                user_data[sender_id]["state"] = "waiting_urgency"
            elif user_data[sender_id]["state"] == "waiting_urgency":
                urgency = message
                order_or_issue = user_data[sender_id].get("order_number", user_data[sender_id].get("issue", ""))
                send_message(sender_id, f"A team member will follow up soon on your {('order' if 'order_number' in user_data[sender_id] else 'issue')} ({urgency}). Anything else?",
                             quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                             platform=platform)
                del user_data[sender_id]  # Clear user data after urgency response
            elif user_data[sender_id]["state"] == "waiting_lead":
                parts = message.split("\n")
                lead_data = user_data[sender_id]["lead_data"]
                if len(parts) >= 1:
                    lead_data["name"] = parts[0].strip()
                if len(parts) >= 2:
                    lead_data["email"] = parts[1].strip()
                if len(parts) >= 3:
                    lead_data["phone"] = parts[2].strip() if parts[2].strip() else None
                if len(parts) >= 4:
                    lead_data["company"] = parts[3].strip() if parts[3].strip() else None
                send_message(sender_id, "Thanks for your info! We’ll reach out soon. Anything else?",
                             quick_replies=[{"title": "Back to Main Menu", "payload": "start"}],
                             platform=platform)
                del user_data[sender_id]  # Clear user data after lead capture
        else:
            send_message(sender_id, "Sorry, I didn’t understand that. Try selecting an option or type 'start'.",
                         quick_replies=[{"title": "Services", "payload": "services"},
                                        {"title": "FAQs", "payload": "faq"},
                                        {"title": "Support", "payload": "support"},
                                        {"title": "Sales", "payload": "sales"},
                                        {"title": "Contact Us", "payload": "contact"}],
                         platform=platform)

# ✅ Send Messages (Multi-Platform Compatible)
def send_message(sender_id, text, quick_replies=None, platform="meta"):
    if platform == "meta":
        if not FB_PAGE_TOKEN:
            logger.warning("FB_PAGE_TOKEN not set. Skipping Meta message.")
            return
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
        try:
            response = requests.post(url, json=payload, headers=headers)
            logger.info("🔹 Meta API Response: %s", response.json())
        except requests.exceptions.RequestException as e:
            logger.error("🔹 Failed to send Meta message: %s", str(e))
            if response.status_code == 400 and "You cannot send messages to this id" in str(response.json()):
                logger.warning("Skipping message to invalid sender_id: %s", sender_id)
    elif platform == "wechat":
        if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
            logger.warning("WeChat credentials not set. Skipping WeChat message.")
            return
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
        try:
            response = requests.post(url, json=payload, headers=headers)
            logger.info("🔹 WeChat API Response: %s", response.json())
        except requests.exceptions.RequestException as e:
            logger.error("🔹 Failed to send WeChat message: %s", str(e))

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