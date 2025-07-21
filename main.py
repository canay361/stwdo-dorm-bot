from flask import Flask
from threading import Thread
import os
import time
import hashlib
import logging
from datetime import datetime
import requests

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

class STWDOTelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.website_url = "https://www.stwdo.de/en/living-houses-application/current-housing-offers"
        self.check_interval = 30  # seconds
        self.last_hash = None
        self.no_results_text = "No results found for the given search criteria"
        
        if not self.bot_token or not self.chat_id:
            logging.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables!")
            raise ValueError("Telegram configuration missing")
    
    def send_telegram_message(self, message):
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            logging.info("Telegram message sent successfully")
            return True
        except Exception as e:
            logging.error(f"Failed to send Telegram message: {e}")
            return False
    
    def fetch_page_content(self):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0',
            }
            response = requests.get(self.website_url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logging.error(f"Error fetching page: {e}")
            return None
    
    def check_for_rooms(self, content):
        if content is None:
            return False, "Could not fetch page content"
        has_no_results = self.no_results_text in content
        current_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        if self.last_hash is None:
            self.last_hash = current_hash
            return False, "Initial check completed"
        content_changed = current_hash != self.last_hash
        self.last_hash = current_hash
        if content_changed and not has_no_results:
            return True, "🏠 ROOMS AVAILABLE! The 'No results found' message is gone!"
        elif content_changed:
            return False, "Page changed but still showing 'No results found'"
        else:
            return False, "No changes detected"
    
    def run_monitoring(self):
        logging.info("🤖 STWDO Telegram Bot started!")
        startup_msg = f"""
🤖 <b>STWDO Dorm Monitor Started!</b>

📍 Monitoring: <a href="{self.website_url}">STWDO Housing Offers</a>
⏰ Checking every {self.check_interval} seconds
🏠 You'll be notified instantly when rooms become available!

<i>Bot is now running 24/7...</i>
        """
        self.send_telegram_message(startup_msg.strip())
        
        consecutive_errors = 0
        max_errors = 5
        
        while True:
            try:
                logging.info("🔍 Checking for room updates...")
                content = self.fetch_page_content()
                rooms_available, status_msg = self.check_for_rooms(content)
                
                if rooms_available:
                    alert_msg = f"""
🚨 <b>URGENT: DORM ROOMS AVAILABLE!</b> 🚨

🏠 Rooms are now listed on the STWDO website!
⚡ Only 10 spots per room - ACT FAST!

🔗 <b><a href="{self.website_url}">APPLY NOW ➤ CLICK HERE</a></b>

📅 Detected: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ Remember: You need to submit your application immediately!
                    """
                    for i in range(2):
                        success = self.send_telegram_message(alert_msg.strip())
                        if success:
                            break
                        time.sleep(5)
                    
                    logging.warning("🚨 ROOM ALERT SENT! 🚨")
                    
                    tips_msg = f"""
📋 <b>Quick Application Tips:</b>

1️⃣ Have your documents ready
2️⃣ Fill forms completely
3️⃣ Submit as fast as possible
4️⃣ Check for multiple room options

🔗 <a href="{self.website_url}">Direct link to applications</a>

<i>Good luck! 🍀</i>
                    """
                    time.sleep(10)
                    self.send_telegram_message(tips_msg.strip())
                else:
                    logging.info(f"Status: {status_msg}")
                
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logging.error(f"Error in monitoring loop: {e}")
                if consecutive_errors >= max_errors:
                    self.send_telegram_message(f"⚠️ Bot encountered {max_errors} consecutive errors. Restarting monitoring...")
                    consecutive_errors = 0
            
            time.sleep(self.check_interval)

def start_bot():
    bot = STWDOTelegramBot()
    bot.run_monitoring()

if __name__ == "__main__":
    # Start Flask app in a separate thread
    flask_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000))))
    flask_thread.start()

    # Start the bot monitoring loop
    start_bot()
