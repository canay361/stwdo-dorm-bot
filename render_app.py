#!/usr/bin/env python3
"""
Simplified app for Render deployment with better error handling
"""

import os
import logging
from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import hashlib
import time
import threading
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback-secret")

# Global monitoring variables
monitor_thread = None
is_monitoring = False
last_hash = ""
last_check = None
logs = []

# Configuration from environment
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID") 
MONITOR_URL = "https://www.stwdo.de/wohnen/aktuelle-wohnangebote"
CHECK_INTERVAL = 30

def add_log(message, level="info"):
    """Add log entry"""
    global logs
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"timestamp": timestamp, "message": message, "level": level}
    logs.append(log_entry)
    if len(logs) > 50:  # Keep only last 50 logs
        logs.pop(0)
    logger.info(f"{message}")

def send_telegram(message):
    """Send Telegram notification"""
    if not BOT_TOKEN or not CHAT_ID:
        add_log("Telegram not configured", "warning")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": message}
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        add_log("Telegram notification sent", "success")
        return True
    except Exception as e:
        add_log(f"Telegram error: {str(e)}", "error")
        return False

def check_website():
    """Check website for changes"""
    global last_hash, last_check
    
    try:
        response = requests.get(MONITOR_URL, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        content = soup.get_text()
        current_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        
        last_check = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if last_hash and current_hash != last_hash:
            change_msg = f"🏠 Dorm room change detected!\n\nCheck: {MONITOR_URL}"
            add_log("CHANGE DETECTED!", "success")
            send_telegram(change_msg)
        else:
            if not last_hash:
                add_log("Initial content captured", "info")
            else:
                add_log("No changes detected", "info")
        
        last_hash = current_hash
        return True
        
    except Exception as e:
        add_log(f"Check failed: {str(e)}", "error")
        return False

def monitor_loop():
    """Main monitoring loop"""
    global is_monitoring
    add_log("Monitoring started", "success")
    
    while is_monitoring:
        check_website()
        time.sleep(CHECK_INTERVAL)
    
    add_log("Monitoring stopped", "info")

@app.route('/')
def status():
    """Status endpoint"""
    return jsonify({
        "status": "running" if is_monitoring else "stopped",
        "last_check": last_check,
        "logs": logs[-10:],  # Last 10 logs
        "config": {
            "url": MONITOR_URL,
            "interval": CHECK_INTERVAL,
            "telegram_configured": bool(BOT_TOKEN and CHAT_ID)
        }
    })

@app.route('/start', methods=['POST'])
def start_monitoring():
    """Start monitoring"""
    global monitor_thread, is_monitoring
    
    if is_monitoring:
        return jsonify({"message": "Already monitoring"}), 400
    
    if not BOT_TOKEN or not CHAT_ID:
        return jsonify({"error": "Telegram not configured"}), 400
    
    is_monitoring = True
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    
    return jsonify({"message": "Monitoring started"})

@app.route('/stop', methods=['POST'])
def stop_monitoring():
    """Stop monitoring"""
    global is_monitoring
    is_monitoring = False
    return jsonify({"message": "Monitoring stopped"})

@app.route('/logs')
def get_logs():
    """Get logs"""
    return jsonify({"logs": logs})

@app.route('/test', methods=['POST'])
def test_telegram():
    """Test Telegram"""
    result = send_telegram("🏠 Test message from Dorm Monitor! If you see this, notifications work perfectly.")
    return jsonify({"success": result})

# Auto-start monitoring if credentials are available
def auto_start():
    """Auto-start monitoring on app startup"""
    if BOT_TOKEN and CHAT_ID:
        global is_monitoring, monitor_thread
        add_log("Auto-starting monitoring", "info")
        is_monitoring = True
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()

# Call auto_start when app is created
with app.app_context():
    auto_start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)