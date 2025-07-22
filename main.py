from flask import Flask
from threading import Thread
import os
import time
import hashlib
import logging
from datetime import datetime
import requests
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

@app.route("/")
def home():
    return "STWDO Bot is running!"

@app.route("/status")
def status():
    return {"status": "active", "timestamp": datetime.now().isoformat()}

class STWDOTelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.website_url = "https://www.stwdo.de/en/living-houses-application/current-housing-offers"
        self.check_interval = 30  # seconds
        self.last_hash = None
        self.no_results_text = "No results found for the given search criteria"
        self.room_indicators = ["room", "flat", "apartment", "housing", "apply", "EUR", "€"]
        self.is_first_run = True
        
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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            session = requests.Session()
            response = session.get(self.website_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Wait a bit to let any JavaScript load
            time.sleep(2)
            
            return response.text
        except Exception as e:
            logging.error(f"Error fetching page: {e}")
            return None
    
    def analyze_content(self, content):
        """Analyze content for room availability with multiple detection methods"""
        if content is None:
            return False, "Could not fetch page content", {}
        
        # Method 1: Check for "no results" text
        has_no_results = self.no_results_text in content
        
        # Method 2: Look for room indicators
        room_count = 0
        for indicator in self.room_indicators:
            room_count += content.lower().count(indicator.lower())
        
        # Method 3: Look for price indicators (EUR, €)
        price_indicators = len(re.findall(r'(EUR|\€|\d+\s*€|\d+\s*EUR)', content))
        
        # Method 4: Look for application links/forms
        apply_links = content.lower().count('apply') + content.lower().count('application')
        
        # Method 5: Content length analysis (rooms = more content)
        content_length = len(content.strip())
        
        analysis = {
            "has_no_results": has_no_results,
            "room_indicators": room_count,
            "price_indicators": price_indicators,
            "apply_links": apply_links,
            "content_length": content_length,
            "timestamp": datetime.now().strftime('%H:%M:%S')
        }
        
        # Determine if rooms are available
        rooms_available = False
        confidence = 0
        
        if not has_no_results:
            confidence += 3
        if room_count > 5:  # Reasonable threshold
            confidence += 2
        if price_indicators > 0:
            confidence += 2
        if apply_links > 0:
            confidence += 1
        if content_length > 5000:  # Longer content suggests listings
            confidence += 1
            
        rooms_available = confidence >= 4  # Need at least 4 points
        
        status_msg = f"Analysis: no_results={has_no_results}, rooms={room_count}, prices={price_indicators}, confidence={confidence}"
        
        return rooms_available, status_msg, analysis
    
    def check_for_rooms(self, content):
        """Main room detection logic"""
        rooms_available, status_msg, analysis = self.analyze_content(content)
        
        # Hash-based change detection
        current_hash = hashlib.md5(content.encode('utf-8')).hexdigest() if content else "empty"
        
        if self.last_hash is None:
            self.last_hash = current_hash
            # On first run, if we detect rooms, send notification
            if rooms_available and not self.is_first_run:
                return True, "Rooms detected on startup!"
            return False, f"Initial check: {status_msg}"
        
        content_changed = current_hash != self.last_hash
        self.last_hash = current_hash
        
        if content_changed:
            logging.info(f"Content changed! {status_msg}")
            if rooms_available:
                return True, f"🏠 ROOMS AVAILABLE! {status_msg}"
            else:
                return False, f"Content changed but no rooms detected: {status_msg}"
        
        # Even if content hasn't changed, check if we missed rooms on first run
        if self.is_first_run and rooms_available:
            return True, f"Rooms found on initial scan: {status_msg}"
        
        return False, f"No changes: {status_msg}"
    
    def run_monitoring(self):
        logging.info("🤖 STWDO Telegram Bot started!")
        
        # Send startup message
        startup_msg = f"""
🤖 <b>STWDO Dorm Monitor Started!</b>

📍 Monitoring: <a href="{self.website_url}">STWDO Housing Offers</a>
⏰ Checking every {self.check_interval} seconds
🏠 You'll be notified instantly when rooms become available!

<i>Bot is now running 24/7...</i>

🔧 <b>Enhanced Detection:</b>
• Content change monitoring
• Room keyword analysis  
• Price indicator detection
• Application link scanning
        """
        self.send_telegram_message(startup_msg.strip())
        
        consecutive_errors = 0
        max_errors = 5
        
        while True:
            try:
                logging.info("🔍 Checking for room updates...")
                content = self.fetch_page_content()
                rooms_available, status_msg = self.check_for_rooms(content)
                
                # Mark first run as complete
                if self.is_first_run:
                    self.is_first_run = False
                
                if rooms_available:
                    # ROOMS FOUND - Send urgent notification!
                    alert_msg = f"""
🚨 <b>URGENT: DORM ROOMS AVAILABLE!</b> 🚨

🏠 Rooms detected on STWDO website!
⚡ Only 10 spots per room - ACT FAST!

🔗 <b><a href="{self.website_url}">APPLY NOW ➤ CLICK HERE</a></b>

📅 Detected: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🔍 Detection: {status_msg}

⚠️ Remember: Submit your application immediately!
                    """
                    
                    # Send multiple times to ensure delivery
                    for i in range(2):
                        success = self.send_telegram_message(alert_msg.strip())
                        if success:
                            break
                        time.sleep(5)
                    
                    logging.warning("🚨 ROOM ALERT SENT! 🚨")
                    
                    # Send follow-up tips
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
                
                consecutive_errors = 0  # Reset error counter
                
            except Exception as e:
                consecutive_errors += 1
                logging.error(f"Error in monitoring loop: {e}")
                
                if consecutive_errors >= max_errors:
                    error_msg = f"⚠️ Bot encountered {max_errors} consecutive errors. Still monitoring..."
                    self.send_telegram_message(error_msg)
                    consecutive_errors = 0
            
            # Wait before next check
            time.sleep(self.check_interval)

def start_bot():
    try:
        bot = STWDOTelegramBot()
        bot.run_monitoring()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")

if __name__ == "__main__":
    # Start Flask app in a separate thread for cloud hosting
    flask_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000))))
    flask_thread.daemon = True
    flask_thread.start()
    
    # Give Flask time to start
    time.sleep(2)
    logging.info("Flask server started")
    
    # Start the bot monitoring
    start_bot()
