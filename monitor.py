import requests
from bs4 import BeautifulSoup
import hashlib
import time
import os
import threading
from datetime import datetime
import logging

try:
    import telegram
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logging.warning("python-telegram-bot not available. Telegram notifications will be disabled.")

class DormMonitor:
    def __init__(self):
        self.url = ""
        self.bot_token = ""
        self.chat_id = ""
        self.check_interval = 30
        self.previous_hash = ""
        self.is_running = False
        self.monitor_thread = None
        self.logs = []
        self.bot = None
        self.last_check_time = None
        self.last_check_status = "Never checked"
        self.lock = threading.Lock()
        
    def configure(self, url, bot_token, chat_id, check_interval):
        """Configure the monitor settings"""
        self.url = url
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.check_interval = max(10, check_interval)  # Minimum 10 seconds
        
        # Set bot to a simple marker - we'll validate on first use
        if bot_token and chat_id:
            self.bot = "configured"  # Simple marker that we have credentials
        else:
            self.bot = None
        
        self.add_log("Configuration updated successfully", "success")
    
    def get_config(self):
        """Get current configuration"""
        with self.lock:
            return {
                'url': self.url,
                'bot_token': self.bot_token,
                'chat_id': self.chat_id,
                'check_interval': self.check_interval
            }
    
    def get_status(self):
        """Get current monitoring status"""
        with self.lock:
            return {
                'is_running': self.is_running,
                'last_check_time': self.last_check_time,
                'last_check_status': self.last_check_status,
                'configured': bool(self.url and self.bot_token and self.chat_id)
            }
    
    def get_logs(self):
        """Get monitoring logs"""
        with self.lock:
            return self.logs.copy()
    
    def add_log(self, message, level="info"):
        """Add a log entry"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = {
            'timestamp': timestamp,
            'message': message,
            'level': level
        }
        
        with self.lock:
            self.logs.append(log_entry)
            # Keep only last 100 log entries
            if len(self.logs) > 100:
                self.logs.pop(0)
        
        # Also log to console
        if level == "error":
            logging.error(f"{timestamp} - {message}")
        elif level == "warning":
            logging.warning(f"{timestamp} - {message}")
        else:
            logging.info(f"{timestamp} - {message}")
    
    def clear_logs(self):
        """Clear all logs"""
        with self.lock:
            self.logs.clear()
    
    def send_telegram_message(self, message):
        """Send a message to Telegram"""
        if not self.bot_token or not self.chat_id:
            self.add_log("Cannot send Telegram message: Bot not configured", "error")
            return False
        
        try:
            # Use requests to send message directly to Telegram API
            # This avoids async/await complications
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': message
            }
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            
            self.add_log("Telegram notification sent successfully", "success")
            return True
        except Exception as e:
            self.add_log(f"Error sending Telegram message: {str(e)}", "error")
            return False
    
    def check_website(self):
        """Check the website for changes"""
        if not self.url:
            self.add_log("Cannot check website: URL not configured", "error")
            return False
        
        try:
            # Get the content of the webpage
            response = requests.get(self.url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, "html.parser")
            current_content = soup.get_text()
            
            # Create a hash of the current content
            current_hash = hashlib.md5(current_content.encode("utf-8")).hexdigest()
            
            with self.lock:
                self.last_check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Compare the current hash with the previous hash
            if self.previous_hash and current_hash != self.previous_hash:
                self.add_log("Change detected on the website!", "success")
                with self.lock:
                    self.last_check_status = "Change detected!"
                
                # Send Telegram notification
                message = f"🏠 A new dorm room might be available!\n\nCheck the website now: {self.url}"
                self.send_telegram_message(message)
                
            else:
                with self.lock:
                    self.last_check_status = "No changes detected"
                if not self.previous_hash:
                    self.add_log("Initial website content captured", "info")
                else:
                    self.add_log("No changes detected", "info")
            
            # Update the previous hash
            self.previous_hash = current_hash
            return True
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Could not connect to the website: {str(e)}"
            self.add_log(error_msg, "error")
            with self.lock:
                self.last_check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.last_check_status = "Connection error"
            return False
        except Exception as e:
            error_msg = f"An unexpected error occurred: {str(e)}"
            self.add_log(error_msg, "error")
            with self.lock:
                self.last_check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.last_check_status = "Error"
            return False
    
    def monitor_loop(self):
        """Main monitoring loop"""
        self.add_log("Monitoring started", "success")
        
        while self.is_running:
            self.check_website()
            
            # Sleep for the specified interval, but check every second if we should stop
            for _ in range(self.check_interval):
                if not self.is_running:
                    break
                time.sleep(1)
        
        self.add_log("Monitoring stopped", "info")
    
    def start(self):
        """Start monitoring in a background thread"""
        if not (self.url and self.bot_token and self.chat_id):
            self.add_log("Cannot start monitoring: Configuration incomplete", "error")
            return False
        
        with self.lock:
            if self.is_running:
                self.add_log("Monitoring is already running", "warning")
                return False
            
            self.is_running = True
        
        try:
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
            return True
        except Exception as e:
            with self.lock:
                self.is_running = False
            self.add_log(f"Error starting monitoring thread: {str(e)}", "error")
            return False
    
    def stop(self):
        """Stop monitoring"""
        with self.lock:
            if not self.is_running:
                return
            
            self.is_running = False
        
        # Wait for thread to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
    
    def manual_check(self):
        """Perform a manual website check"""
        if not self.url:
            self.add_log("Cannot perform manual check: URL not configured", "error")
            return False
        
        self.add_log("Performing manual check...", "info")
        return self.check_website()
