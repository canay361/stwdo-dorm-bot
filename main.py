from flask import Flask
from threading import Thread
import os
import time
import hashlib
import logging
from datetime import datetime
import requests
import re
# Selenium imports removed for lighter deployment

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
        self.check_interval = 45  # Check every 45 seconds
        self.last_hash = None
        self.last_content_length = 0
        self.no_results_text = "No results found for the given search criteria"
        self.is_first_run = True
        # Removed Selenium driver initialization
        
        if not self.bot_token or not self.chat_id:
            logging.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables!")
            raise ValueError("Telegram configuration missing")
    
    def setup_driver(self):
        """Setup headless Chrome driver for JavaScript-heavy sites"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Try to create driver
            self.driver = webdriver.Chrome(options=chrome_options)
            logging.info("✅ Selenium WebDriver initialized successfully")
            return True
        except Exception as e:
            logging.warning(f"⚠️ Could not initialize Selenium: {e}. Falling back to requests.")
            self.driver = None
            return False
    
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
    
    def fetch_page_content_selenium(self):
        """Fetch content using Selenium to handle JavaScript"""
        try:
            if not self.driver:
                return None
                
            self.driver.get(self.website_url)
            
            # Wait for page to load
            WebDriverWait(self.driver, 20).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Wait a bit more for any dynamic content
            time.sleep(5)
            
            # Get page source after JavaScript execution
            content = self.driver.page_source
            logging.info(f"Selenium: Fetched {len(content)} characters")
            return content
            
        except Exception as e:
            logging.error(f"Selenium fetch error: {e}")
            return None
    
    def fetch_page_content_requests(self):
        """Fallback method using requests"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
            
            session = requests.Session()
            response = session.get(self.website_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            logging.info(f"Requests: Fetched {len(response.text)} characters")
            return response.text
            
        except Exception as e:
            logging.error(f"Requests fetch error: {e}")
            return None
    
    def fetch_page_content(self):
        """Try Selenium first, fallback to requests"""
        # Try Selenium first (better for JavaScript sites)
        content = self.fetch_page_content_selenium()
        if content:
            return content
            
        # Fallback to requests
        return self.fetch_page_content_requests()
    
    def advanced_room_detection(self, content):
        """Enhanced room detection with multiple strategies"""
        if not content:
            return False, "No content to analyze", {}
        
        content_lower = content.lower()
        
        # Strategy 1: Check for explicit "no results" message
        has_no_results = self.no_results_text.lower() in content_lower
        
        # Strategy 2: Look for room/housing related keywords
        room_keywords = [
            'apply now', 'application', 'room', 'apartment', 'flat', 'housing',
            'available', 'vacancy', 'zimmer', 'wohnung', 'verfügbar', 'bewerbung',
            'residential complex', 'dormitory', 'student housing'
        ]
        keyword_matches = sum(1 for keyword in room_keywords if keyword in content_lower)
        
        # Strategy 3: Look for price indicators
        price_patterns = [
            r'\d+[.,]\d+\s*€',  # 123.45 €
            r'\d+\s*€',         # 123 €
            r'€\s*\d+',         # € 123
            r'\d+[.,]\d+\s*eur', # 123.45 EUR
            r'rent',
            r'miete'
        ]
        price_matches = sum(1 for pattern in price_patterns if re.search(pattern, content_lower))
        
        # Strategy 4: Look for application forms/buttons
        form_indicators = [
            'form', 'submit', 'apply', 'bewerbung', 'anmelden', 'button',
            'input', 'select', 'bewerben'
        ]
        form_matches = sum(1 for indicator in form_indicators if indicator in content_lower)
        
        # Strategy 5: Content structure analysis
        content_length = len(content.strip())
        
        # Strategy 6: Look for specific STWDO housing indicators
        stwdo_indicators = [
            'residential complex', 'wohnanlage', 'studentenwohnen',
            'dortmund', 'hagen', 'iserlohn', 'soest'
        ]
        stwdo_matches = sum(1 for indicator in stwdo_indicators if indicator in content_lower)
        
        # Strategy 7: Detect significant content changes (could indicate new listings)
        content_change_significant = abs(content_length - self.last_content_length) > 1000
        self.last_content_length = content_length
        
        analysis = {
            "has_no_results": has_no_results,
            "keyword_matches": keyword_matches,
            "price_matches": price_matches,
            "form_matches": form_matches,
            "content_length": content_length,
            "stwdo_matches": stwdo_matches,
            "content_change_significant": content_change_significant,
            "timestamp": datetime.now().strftime('%H:%M:%S')
        }
        
        # Scoring system (more lenient than before)
        score = 0
        
        # Strong positive indicators
        if not has_no_results:
            score += 3
        if price_matches > 0:
            score += 2
        if form_matches > 2:
            score += 2
        if keyword_matches > 5:
            score += 2
            
        # Moderate indicators
        if stwdo_matches > 0:
            score += 1
        if content_length > 8000:  # Substantial content
            score += 1
        if content_change_significant:
            score += 1
        
        # Decision threshold (lowered from 4 to 3)
        rooms_available = score >= 3
        
        status_msg = f"Score: {score}, no_results={has_no_results}, keywords={keyword_matches}, prices={price_matches}, forms={form_matches}"
        
        logging.info(f"Room detection: {status_msg}")
        
        return rooms_available, status_msg, analysis
    
    def check_for_rooms(self, content):
        """Main room detection logic with improved change detection"""
        rooms_available, status_msg, analysis = self.advanced_room_detection(content)
        
        # Create hash for change detection
        if content:
            # Use a more sensitive hash that includes key indicators
            hash_content = f"{content[:5000]}-{analysis['keyword_matches']}-{analysis['price_matches']}-{analysis['form_matches']}"
            current_hash = hashlib.md5(hash_content.encode('utf-8')).hexdigest()
        else:
            current_hash = "empty"
        
        # First run logic
        if self.last_hash is None:
            self.last_hash = current_hash
            if rooms_available and not self.is_first_run:
                return True, f"Rooms detected on startup! {status_msg}"
            return False, f"Initial check: {status_msg}"
        
        # Check for changes
        content_changed = current_hash != self.last_hash
        self.last_hash = current_hash
        
        if content_changed:
            logging.info(f"Content changed detected! {status_msg}")
            if rooms_available:
                return True, f"🏠 NEW ROOMS AVAILABLE! {status_msg}"
            else:
                # Even if no rooms detected, significant changes might indicate rooms
                if analysis['content_change_significant']:
                    return True, f"⚠️ SIGNIFICANT CHANGE detected (possible rooms): {status_msg}"
                return False, f"Content changed but no rooms: {status_msg}"
        
        # Check if we have rooms but missed them on first run
        if self.is_first_run and rooms_available:
            return True, f"Rooms found on initial scan: {status_msg}"
        
        return False, f"No changes: {status_msg}"
    
    def run_monitoring(self):
        logging.info("🤖 STWDO Telegram Bot started!")
        
        # Try to setup Selenium
        selenium_available = self.setup_driver()
        
        # Send startup message
        method_info = "with Selenium WebDriver" if selenium_available else "with requests only"
        startup_msg = f"""
🤖 <b>STWDO Dorm Monitor Started!</b> {method_info}

📍 Monitoring: <a href="{self.website_url}">STWDO Housing Offers</a>
⏰ Checking every {self.check_interval} seconds
🏠 Enhanced detection with lower thresholds!

<i>Bot is now running 24/7...</i>

🔧 <b>Improvements:</b>
• JavaScript content loading support
• More sensitive change detection
• Lower detection thresholds
• Multiple detection strategies
        """
        self.send_telegram_message(startup_msg.strip())
        
        consecutive_errors = 0
        max_errors = 3
        
        try:
            while True:
                try:
                    logging.info("🔍 Checking for room updates...")
                    content = self.fetch_page_content()
                    
                    if content:
                        rooms_available, status_msg = self.check_for_rooms(content)
                        
                        # Mark first run as complete
                        if self.is_first_run:
                            self.is_first_run = False
                        
                        if rooms_available:
                            # ROOMS FOUND - Send alert!
                            alert_msg = f"""
🚨 <b>URGENT: DORM ROOMS AVAILABLE!</b> 🚨

🏠 Rooms detected on STWDO website!
⚡ Act fast - limited spots available!

🔗 <b><a href="{self.website_url}">CHECK NOW ➤ CLICK HERE</a></b>

📅 Detected: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🔍 Detection: {status_msg}

⚠️ Apply immediately if you see available rooms!
                            """
                            
                            # Send notification
                            success = self.send_telegram_message(alert_msg.strip())
                            if success:
                                logging.warning("🚨 ROOM ALERT SENT! 🚨")
                            
                        else:
                            logging.info(f"Status: {status_msg}")
                    else:
                        logging.warning("Failed to fetch content")
                    
                    consecutive_errors = 0
                    
                except Exception as e:
                    consecutive_errors += 1
                    logging.error(f"Error in monitoring loop: {e}")
                    
                    if consecutive_errors >= max_errors:
                        error_msg = f"⚠️ Bot encountered {max_errors} consecutive errors. Still monitoring..."
                        self.send_telegram_message(error_msg)
                        consecutive_errors = 0
                
                # Wait before next check
                time.sleep(self.check_interval)
                
        finally:
            # Clean up Selenium driver
            if self.driver:
                try:
                    self.driver.quit()
                    logging.info("Selenium driver closed")
                except:
                    pass

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
