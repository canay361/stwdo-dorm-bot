from flask import Flask
from threading import Thread
import os
import time
import hashlib
import logging
from datetime import datetime
import requests
import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

@app.route("/test")
def test():
    """Test endpoint to manually trigger a check"""
    try:
        bot = STWDOTelegramBot()
        content = bot.fetch_page_content()
        if content:
            rooms_available, message, analysis = bot.analyze_page_content(content)
            
            # Extract some sample text to help debug
            soup = BeautifulSoup(content, 'html.parser')
            listings = soup.select('.housing-offer-item, .offer-item')  # Common listing classes
            
            sample_listings = []
            for idx, listing in enumerate(listings[:5]):  # First 5 listings
                title = listing.get_text(' ', strip=True)[:100]
                sample_listings.append(f"{idx+1}. {title}")
            
            return {
                "rooms_available": rooms_available,
                "message": message,
                "analysis": analysis,
                "content_length": len(content),
                "listings_count": len(listings),
                "sample_listings": sample_listings,
                "contains_no_results": bool(soup.find(string=re.compile(r'no results found', re.I)))
        return {"error": "Could not fetch content"}
    except Exception as e:
        return {"error": str(e)}

class STWDOTelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.website_url = "https://www.stwdo.de/en/living-houses-application/current-housing-offers"
        self.german_url = "https://www.stwdo.de/de/wohnen-bewerben/aktuelle-wohnungsangebote"
        self.check_interval = 300  # 5 minutes between checks
        self.last_hash = None
        self.last_rooms_status = None
        
        if not self.bot_token or not self.chat_id:
            logging.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables!")
            raise ValueError("Telegram configuration missing")
        
        logging.info(f"Bot initialized - Chat ID: {self.chat_id}")
    
    def init_webdriver(self):
        """Initialize remote WebDriver using free Selenium Grid"""
        try:
            # Choose one of these free Selenium Grid providers:
            selenium_url = "http://demo.zalenium.com/wd/hub"  # Free public Zalenium
            # selenium_url = "https://USERNAME:ACCESS_KEY@hub.lambdatest.com/wd/hub"  # LambdaTest (sign up required)
            
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            
            driver = webdriver.Remote(
                command_executor=selenium_url,
                options=options
            )
            return driver
        except Exception as e:
            logging.error(f"Failed to initialize remote WebDriver: {e}")
            raise
    
    def send_telegram_message(self, message):
        """Send message to Telegram with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                data = {
                    'chat_id': self.chat_id,
                    'text': message,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': False
                }
                response = requests.post(url, data=data, timeout=15)
                response.raise_for_status()
                logging.info(f"Telegram message sent successfully (attempt {attempt + 1})")
                return True
            except Exception as e:
                logging.error(f"Failed to send Telegram message (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        return False
    
    def fetch_page_content(self):
        """Fetch the STWDO website content using remote Selenium"""
        driver = None
        try:
            driver = self.init_webdriver()
            
            # Try English version first
            driver.get(self.website_url)
            
            # Wait longer for remote Selenium (30 seconds)
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".housing-offer-item, .offer-item, .no-results, .noResults")
                    )
                )
            except:
                pass  # Fallback to raw page source
            
            content = driver.page_source
            
            # If English page shows no results, try German version
            if "no results found" in content.lower():
                driver.get(self.german_url)
                try:
                    WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, ".housing-offer-item, .offer-item, .no-results, .keine-ergebnisse")
                        )
                    )
                except:
                    pass
                content = driver.page_source
            
            logging.info(f"Fetched {len(content)} characters from website")
            return content
            
        except Exception as e:
            logging.error(f"Error fetching page content: {e}")
            return None
        finally:
            if driver:
                driver.quit()
    
    def analyze_page_content(self, content):
        """Analyze the STWDO page for available rooms"""
        if not content:
            return False, "No content to analyze", {}
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # Look for listings - update selectors if needed
        listings = soup.select('.housing-offer-item, .offer-item, .list-item, .result-item')
        
        # Check for "no results" messages
        no_results = soup.find(string=re.compile(r'no results found|keine ergebnisse gefunden', re.I))
        
        analysis = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "listings_count": len(listings),
            "has_no_results_message": bool(no_results),
            "content_length": len(content)
        }
        
        if no_results:
            return False, "No rooms available (explicit message found)", analysis
        
        if listings:
            # Extract basic info from listings
            rooms_info = []
            for listing in listings[:5]:  # First 5 listings
                title = listing.get_text(' ', strip=True)[:100]
                rooms_info.append(title)
            
            analysis["sample_listings"] = rooms_info
            return True, f"Found {len(listings)} potential rooms", analysis
        
        return False, "No clear room listings detected", analysis
    
    def check_for_updates(self, content):
        """Check for content changes and room availability"""
        if not content:
            return False, "No content retrieved", None
        
        rooms_available, status_msg, analysis = self.analyze_page_content(content)
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        # First run initialization
        if self.last_hash is None:
            self.last_hash = content_hash
            self.last_rooms_status = rooms_available
            return rooms_available, f"Initial check: {status_msg}", analysis
        
        # Check for changes
        content_changed = content_hash != self.last_hash
        status_changed = rooms_available != self.last_rooms_status
        
        self.last_hash = content_hash
        self.last_rooms_status = rooms_available
        
        if rooms_available and (content_changed or status_changed):
            return True, f"🚨 ROOMS AVAILABLE! {status_msg}", analysis
        elif content_changed:
            return False, f"Content changed but no rooms detected: {status_msg}", analysis
        
        return False, f"No changes detected: {status_msg}", analysis
    
    def run_monitoring(self):
        """Main monitoring loop"""
        logging.info("STWDO Dorm Monitor started!")
        
        # Send startup notification
        startup_msg = f"""
🤖 <b>STWDO Dorm Monitor Online!</b>

📍 <b>Monitoring:</b> <a href="{self.website_url}">STWDO Housing Offers</a>
⏰ <b>Check interval:</b> Every {self.check_interval//60} minutes
🌐 <b>Method:</b> Remote browser (no local Chrome needed)

<i>Bot is now running with reliable remote Selenium!</i>
"""
        self.send_telegram_message(startup_msg.strip())
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while True:
            try:
                logging.info("Starting new check...")
                content = self.fetch_page_content()
                
                if content:
                    should_notify, message, analysis = self.check_for_updates(content)
                    
                    if should_notify:
                        alert_msg = f"""
🏠 <b>DORM ROOMS AVAILABLE!</b>

{message}

🔗 <a href="{self.website_url}">Check now and apply immediately!</a>

📊 <b>Details:</b>
• Detected listings: {analysis.get('listings_count', 0)}
• Content length: {analysis.get('content_length', 0)} chars
• Time: {analysis.get('timestamp')}

⚡ <b>Act fast - good rooms go quickly!</b>
"""
                        self.send_telegram_message(alert_msg.strip())
                        logging.info("Sent room availability notification!")
                    
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        self.send_telegram_message("⚠️ Bot is having trouble accessing the website. Please check logs.")
                        consecutive_errors = 0
                
            except Exception as e:
                logging.error(f"Error in monitoring loop: {e}")
                consecutive_errors += 1
            
            time.sleep(self.check_interval)

def start_bot():
    """Start the bot with error handling"""
    try:
        bot = STWDOTelegramBot()
        bot.run_monitoring()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    # Start Flask app in background for Render.com
    flask_thread = Thread(target=lambda: app.run(
        host="0.0.0.0", 
        port=int(os.environ.get("PORT", 10000)),
        debug=False
    ))
    flask_thread.daemon = True
    flask_thread.start()
    time.sleep(3)
    logging.info("Flask server started")
    
    # Start the monitoring bot
    start_bot()
