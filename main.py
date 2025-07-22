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
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            page_text = soup.get_text()
            
            # Look for specific terms in the content
            sample_lines = []
            for line in page_text.split('\n')[:50]:  # First 50 lines
                line = line.strip()
                if line and len(line) > 10:
                    sample_lines.append(line)
            
            return {
                "rooms_available": rooms_available,
                "message": message,
                "analysis": analysis,
                "content_length": len(content),
                "page_text_length": len(page_text),
                "sample_content": sample_lines[:20],  # First 20 meaningful lines
                "contains_zimmer": "zimmer" in content.lower(),
                "contains_dortmund": "dortmund" in content.lower(),
                "contains_wg": "wg" in content.lower(),
                "contains_no_results": "No results found" in content
            }
        return {"error": "Could not fetch content"}
    except Exception as e:
        return {"error": str(e)}

class STWDOTelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.website_url = "https://www.stwdo.de/en/living-houses-application/current-housing-offers"
        self.check_interval = 90  # Check every 90 seconds
        self.last_hash = None
        self.last_rooms_status = None  # Track if rooms were available in last check
        
        # Known messages when no rooms are available
        self.no_rooms_indicators = [
            "No results found for the given search criteria",
            "no results found",
            "keine ergebnisse gefunden",
            "keine ergebnisse",
            "currently no offers available"
        ]
        
        # Positive indicators that rooms are available
        self.positive_room_indicators = [
            # German terms (likely what appears when rooms are available)
            "zimmer", "wohnung", "wg", "frauen-wg", "männer-wg", 
            "dortmund", "hagen", "iserlohn", "soest", "bochum",
            "bewerbung", "bewerben", "verfügbar",
            # English terms
            "room", "flat", "apartment", "women", "men", "shared flat",
            "available", "apply", "application"
        ]
        
        if not self.bot_token or not self.chat_id:
            logging.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables!")
            raise ValueError("Telegram configuration missing")
        
        logging.info(f"Bot initialized - Chat ID: {self.chat_id}")
    
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
                logging.info(f"✅ Telegram message sent successfully (attempt {attempt + 1})")
                return True
            except Exception as e:
                logging.error(f"❌ Failed to send Telegram message (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # Wait before retry
        return False
    
    def fetch_page_content(self):
        """Fetch the STWDO website content with multiple strategies"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',  # German first for better content
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'no-cache, no-store, must-revalidate',  # Force fresh content
                'Pragma': 'no-cache',
                'Expires': '0',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1'
            }
            
            # Use session with cookies for better compatibility
            with requests.Session() as session:
                # First, try the English version
                response = session.get(self.website_url, headers=headers, timeout=30)
                response.raise_for_status()
                
                content = response.text
                logging.info(f"📄 Fetched {len(content)} characters from English page")
                
                # If English page shows no results, try German version
                if "No results found for the given search criteria" in content:
                    german_url = "https://www.stwdo.de/de/wohnen-bewerben/aktuelle-wohnungsangebote"
                    logging.info("🇩🇪 English page shows no results, trying German page...")
                    
                    german_response = session.get(german_url, headers=headers, timeout=30)
                    german_response.raise_for_status()
                    
                    german_content = german_response.text
                    logging.info(f"📄 Fetched {len(german_content)} characters from German page")
                    
                    # Use German content if it has more content or different results
                    if (len(german_content) > len(content) + 500 or 
                        "Keine Ergebnisse" not in german_content):
                        logging.info("🔄 Using German page content (more comprehensive)")
                        content = german_content
                
                return content
                
        except requests.exceptions.RequestException as e:
            logging.error(f"🚫 Network error fetching website: {e}")
            return None
        except Exception as e:
            logging.error(f"🚫 Unexpected error fetching website: {e}")
            return None
    
    def analyze_page_content(self, content):
        """Analyze the STWDO page for available rooms"""
        if not content:
            return False, "No content to analyze", {}
        
        # Parse HTML
        soup = BeautifulSoup(content, 'html.parser')
        page_text = soup.get_text().strip()
        page_text_lower = page_text.lower()
        
        # Initialize analysis
        analysis = {
            "content_length": len(content),
            "page_text_length": len(page_text),
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Check for explicit "no rooms" messages
        has_no_rooms_message = any(
            indicator.lower() in page_text_lower 
            for indicator in self.no_rooms_indicators
        )
        analysis["has_no_rooms_message"] = has_no_rooms_message
        
        # Look for specific room offerings (like "Zimmer in 3er-Frauen-WG")
        room_offering_patterns = [
            r'zimmer\s+in\s+\d+er.*wg',  # "Zimmer in 3er-Frauen-WG"
            r'wohnung.*dortmund',
            r'dortmund.*zimmer',
            r'frauen-wg',
            r'männer-wg',
            r'\d+\s*zimmer.*wg',
            r'wg.*zimmer'
        ]
        
        room_pattern_matches = sum(
            1 for pattern in room_offering_patterns 
            if re.search(pattern, page_text_lower, re.IGNORECASE)
        )
        analysis["room_pattern_matches"] = room_pattern_matches
        
        # Count positive indicators
        positive_count = sum(
            1 for term in self.positive_room_indicators 
            if term in page_text_lower
        )
        analysis["positive_indicators"] = positive_count
        
        # Look for specific STWDO structure elements
        # When rooms are available, there should be clickable adverts/links
        links = soup.find_all('a', href=True)
        room_related_links = []
        for link in links:
            href = link.get('href', '').lower()
            text = link.get_text().lower()
            if any(term in href + ' ' + text for term in ['room', 'flat', 'apartment', 'apply', 'zimmer', 'wohnung']):
                room_related_links.append(link.get('href'))
        
        analysis["room_related_links"] = len(room_related_links)
        
        # Look for forms (application forms)
        forms = soup.find_all('form')
        inputs = soup.find_all(['input', 'button', 'select', 'textarea'])
        analysis["forms_count"] = len(forms)
        analysis["input_elements"] = len(inputs)
        
        # Look for price information
        price_patterns = [
            r'\d+[.,]\d+\s*€',
            r'\d+\s*€', 
            r'€\s*\d+',
            r'\d+[.,]\d+\s*EUR',
            r'\b\d+\s*euro\b'
        ]
        price_matches = sum(1 for pattern in price_patterns if re.search(pattern, page_text, re.IGNORECASE))
        analysis["price_matches"] = price_matches
        
        # Decision logic for room availability
        # Rooms are available if:
        # 1. NO explicit "no rooms" message AND
        # 2. We have room-specific patterns OR substantial positive indicators
        
        rooms_available = False
        confidence_score = 0
        
        if not has_no_rooms_message:
            confidence_score += 3  # Base score if no "no rooms" message
            
        if room_pattern_matches > 0:  # Specific room patterns found (like "Zimmer in 3er-Frauen-WG")
            confidence_score += 4  # High confidence for specific patterns
            
        if positive_count >= 10:  # Many housing-related terms
            confidence_score += 3
        elif positive_count >= 5:
            confidence_score += 2
        elif positive_count >= 3:
            confidence_score += 1
            
        if room_related_links > 0:  # Actual application links
            confidence_score += 2
            
        if price_matches > 0:  # Price information suggests actual listings
            confidence_score += 2
            
        if len(forms) > 0 or len(inputs) > 5:  # Application forms present
            confidence_score += 1
        
        # Consider content length - available rooms page should be longer
        if len(page_text) > 1200:  # More content than just "no results"
            confidence_score += 1
        elif len(page_text) > 800:
            confidence_score += 0.5
            
        analysis["confidence_score"] = confidence_score
        
        # Lower threshold for room availability detection
        rooms_available = confidence_score >= 3
        
        # Generate detailed status message
        status_elements = [
            f"No-rooms-msg: {has_no_rooms_message}",
            f"Room-patterns: {room_pattern_matches}",
            f"Positive: {positive_count}",
            f"Links: {len(room_related_links)}",
            f"Prices: {price_matches}",
            f"Forms: {len(forms)}",
            f"Score: {confidence_score:.1f}"
        ]
        status_msg = " | ".join(status_elements)
        
        logging.info(f"🔍 Analysis: {status_msg} → Rooms Available: {rooms_available}")
        
        return rooms_available, status_msg, analysis
    
    def check_for_updates(self, content):
        """Check for content changes and room availability"""
        if not content:
            return False, "No content retrieved", None
        
        # Analyze current content
        rooms_available, status_msg, analysis = self.analyze_page_content(content)
        
        # Create hash for change detection
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        # Check if this is first run
        if self.last_hash is None:
            self.last_hash = content_hash
            self.last_rooms_status = rooms_available
            
            if rooms_available:
                return True, f"🏠 ROOMS FOUND ON STARTUP! {status_msg}", analysis
            else:
                return False, f"Initial scan complete - no rooms currently. {status_msg}", analysis
        
        # Check for changes
        content_changed = content_hash != self.last_hash
        rooms_status_changed = rooms_available != self.last_rooms_status
        
        # Update tracking
        self.last_hash = content_hash
        notification_needed = False
        notification_msg = ""
        
        if rooms_available and (content_changed or rooms_status_changed):
            # Rooms are available and something changed
            notification_needed = True
            if rooms_status_changed:
                notification_msg = f"🚨 NEW ROOMS AVAILABLE! (Status changed) {status_msg}"
            else:
                notification_msg = f"🚨 ROOMS AVAILABLE! (Content updated) {status_msg}"
                
        elif content_changed and not analysis.get("has_no_rooms_message", True):
            # Content changed and no explicit "no rooms" message
            notification_needed = True
            notification_msg = f"⚠️ WEBSITE UPDATED - Possible new rooms! {status_msg}"
            
        elif rooms_status_changed and not rooms_available:
            # Rooms became unavailable
            logging.info(f"📝 Rooms no longer available: {status_msg}")
        
        # Update room status tracking
        self.last_rooms_status = rooms_available
        
        if notification_needed:
            return True, notification_msg, analysis
        else:
            return False, f"No changes detected. {status_msg}", analysis
    
    def run_monitoring(self):
        """Main monitoring loop"""
        logging.info("🚀 STWDO Telegram Bot started!")
        
        # Send startup notification
        startup_msg = f"""
🤖 <b>STWDO Dorm Monitor Online!</b>

📍 <b>Monitoring:</b> <a href="{self.website_url}">STWDO Housing Offers</a>
⏰ <b>Check interval:</b> Every {self.check_interval} seconds
🎯 <b>Optimized for:</b> STWDO website structure

<b>🔔 You'll be notified when:</b>
• New dorm rooms become available
• Website content changes significantly
• "No results" message disappears

<i>Bot is running 24/7 and ready to catch opportunities!</i>

💡 <b>Tip:</b> When you get a notification, act quickly as rooms fill up fast!
        """
        
        self.send_telegram_message(startup_msg.strip())
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        total_checks = 0
        
        try:
            while True:
                try:
                    total_checks += 1
                    logging.info(f"🔍 Check #{total_checks}: Monitoring STWDO website...")
                    
                    # Fetch and analyze content
                    content = self.fetch_page_content()
                    
                    if content:
                        should_notify, message, analysis = self.check_for_updates(content)
                        
                        if should_notify:
                            # Send notification
                            alert_msg = f"""
{message}

🔗 <b><a href="{self.website_url}">🏠 CHECK WEBSITE NOW ➤</a></b>

📊 <b>Detection Details:</b>
• Confidence Score: {analysis.get('confidence_score', 0)}/7
• Page Length: {analysis.get('page_text_length', 0)} chars
• Room Links Found: {analysis.get('room_related_links', 0)}

📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚡ <b>Next Steps:</b>
1. Click the link above immediately
2. Look for available rooms/flats
3. Apply quickly if you find suitable options!

<i>Remember: Popular rooms get taken within minutes!</i>
                            """
                            
                            success = self.send_telegram_message(alert_msg.strip())
                            if success:
                                logging.warning(f"🚨 ALERT SENT: {message}")
                            else:
                                logging.error("Failed to send alert message")
                        else:
                            logging.info(f"✅ Check complete: {message}")
                        
                        consecutive_errors = 0  # Reset error counter
                        
                    else:
                        consecutive_errors += 1
                        logging.error(f"❌ Failed to fetch content (error #{consecutive_errors})")
                        
                        if consecutive_errors == 5:
                            # Send warning after 5 consecutive errors
                            warning_msg = "⚠️ Bot having trouble accessing STWDO website. Will keep trying..."
                            self.send_telegram_message(warning_msg)
                    
                except KeyboardInterrupt:
                    logging.info("🛑 Bot stopped by user")
                    break
                    
                except Exception as e:
                    consecutive_errors += 1
                    logging.error(f"💥 Unexpected error in monitoring loop: {e}")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        error_msg = f"""
🚨 <b>Bot Error Alert</b>

The bot has encountered {max_consecutive_errors} consecutive errors but is still running.

<b>Last error:</b> {str(e)[:200]}

<i>Monitoring will continue. If issues persist, check the logs.</i>
                        """
                        self.send_telegram_message(error_msg.strip())
                        consecutive_errors = 0  # Reset to prevent spam
                
                # Wait before next check
                logging.info(f"💤 Waiting {self.check_interval} seconds until next check...")
                time.sleep(self.check_interval)
                
        except Exception as critical_error:
            critical_msg = f"""
🆘 <b>Critical Bot Error</b>

The monitoring bot has encountered a critical error and may have stopped.

<b>Error:</b> {str(critical_error)[:300]}

<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please check the application logs and restart if necessary.
            """
            self.send_telegram_message(critical_msg.strip())
            logging.critical(f"Critical error: {critical_error}")
            raise

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
    
    # Give Flask time to start
    time.sleep(3)
    logging.info("🌐 Flask server started")
    
    # Start the monitoring bot
    start_bot()
