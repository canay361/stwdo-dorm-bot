import requests
import time
import hashlib
import logging
from datetime import datetime
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class STWDOTelegramBot:
    def __init__(self):
        # Get these from environment variables (set in cloud service)
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
        """Send message via Telegram bot"""
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
        """Fetch the STWDO housing page content"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            }
            response = requests.get(self.website_url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logging.error(f"Error fetching page: {e}")
            return None
    
    def check_for_rooms(self, content):
        """Check if rooms are available"""
        if content is None:
            return False, "Could not fetch page content"
        
        # Check if the "no results" text is present
        has_no_results = self.no_results_text in content
        
        # Create content hash for change detection
        current_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        # If first run, store hash
        if self.last_hash is None:
            self.last_hash = current_hash
            return False, "Initial check completed"
        
        # Check for changes
        content_changed = current_hash != self.last_hash
        self.last_hash = current_hash
        
        if content_changed and not has_no_results:
            # Content changed AND no "no results" text = rooms available!
            return True, "🏠 ROOMS AVAILABLE! The 'No results found' message is gone!"
        elif content_changed:
            return False, "Page changed but still showing 'No results found'"
        else:
            return False, "No changes detected"
    
    def run_monitoring(self):
        """Main monitoring loop"""
        logging.info("🤖 STWDO Telegram Bot started!")
        logging.info(f"📱 Monitoring: {self.website_url}")
        logging.info(f"⏱️ Check interval: {self.check_interval} seconds")
        
        # Send startup message
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
                    # ROOMS FOUND - Send urgent notification!
                    alert_msg = f"""
🚨 <b>URGENT: DORM ROOMS AVAILABLE!</b> 🚨

🏠 Rooms are now listed on the STWDO website!
⚡ Only 10 spots per room - ACT FAST!

🔗 <b><a href="{self.website_url}">APPLY NOW ➤ CLICK HERE</a></b>

📅 Detected: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ Remember: You need to submit your application immediately!
                    """
                    
                    # Send multiple times to ensure delivery
                    for i in range(2):
                        success = self.send_telegram_message(alert_msg.strip())
                        if success:
                            break
                        time.sleep(5)
                    
                    logging.warning("🚨 ROOM ALERT SENT! 🚨")
                    
                    # Send follow-up with tips
                    tips_msg = f"""
📋 <b>Quick Application Tips:</b>

1️⃣ Have your documents ready
2️⃣ Fill forms completely
3️⃣ Submit as fast as possible
4️⃣ Check for multiple room options

🔗 <a href="{self.website_url}">Direct link to applications</a>

<i>Good luck! 🍀</i>
                    """
                    time.sleep(10)  # Wait before sending tips
                    self.send_telegram_message(tips_msg.strip())
                    
                else:
                    logging.info(f"Status: {status_msg}")
                
                consecutive_errors = 0  # Reset error counter on success
                
            except KeyboardInterrupt:
                logging.info("Bot stopped by user")
                break
            except Exception as e:
                consecutive_errors += 1
                logging.error(f"Error in monitoring loop: {e}")
                
                if consecutive_errors >= max_errors:
                    error_msg = f"⚠️ Bot encountered {max_errors} consecutive errors. Restarting monitoring..."
                    self.send_telegram_message(error_msg)
                    consecutive_errors = 0
            
            # Wait before next check
            time.sleep(self.check_interval)

def main():
    """Entry point for cloud deployment"""
    try:
        bot = STWDOTelegramBot()
        bot.run_monitoring()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        print("Make sure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables are set!")

if __name__ == "__main__":
    main()
