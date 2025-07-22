# GÜNCELLENMİŞ main.py

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

# Logging ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        self.german_url = "https://www.stwdo.de/de/wohnen-bewerben/aktuelle-wohnungsangebote"
        self.check_interval = 60  # 1 dakika
        self.last_hash = None
        self.last_rooms_status = None
        
        if not self.bot_token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID ortam değişkenleri eksik")

    def init_webdriver(self):
        try:
            selenium_url = "http://demo.zalenium.com/wd/hub"
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("user-agent=Mozilla/5.0")

            driver = webdriver.Remote(command_executor=selenium_url, options=options)
            return driver
        except Exception as e:
            logging.error(f"Selenium başlatılamadı: {e}")
            raise

    def fetch_page_content(self):
        driver = None
        try:
            driver = self.init_webdriver()
            driver.get(self.website_url)

            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".housing-offer-item, .offer-item, .no-results")
                )
            )
            content = driver.page_source

            if "no results found" in content.lower():
                driver.get(self.german_url)
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".housing-offer-item, .offer-item, .keine-ergebnisse")
                    )
                )
                content = driver.page_source

            logging.info(f"Sayfa içerik uzunluğu: {len(content)} karakter")
            return content

        except Exception as e:
            logging.error(f"Sayfa içeriği alınamadı: {e}")
            return None
        finally:
            if driver:
                driver.quit()

    def analyze_page_content(self, content):
        soup = BeautifulSoup(content, 'html.parser')
        listings = soup.select('.housing-offer-item, .offer-item, .list-item, .result-item')
        no_results = soup.find(string=re.compile(r'no results found|keine ergebnisse', re.I))

        analysis = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "listings_count": len(listings),
            "has_no_results_message": bool(no_results),
            "content_length": len(content)
        }

        if no_results:
            return False, "No rooms available", analysis
        elif listings:
            rooms_info = [listing.get_text(' ', strip=True)[:100] for listing in listings[:5]]
            analysis["sample_listings"] = rooms_info
            return True, f"{len(listings)} listings found", analysis

        return False, "No listings detected", analysis

    def send_telegram_message(self, message):
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            requests.post(url, data=data, timeout=15)
            logging.info("Telegram mesajı gönderildi.")
        except Exception as e:
            logging.error(f"Telegram mesajı gönderilemedi: {e}")

    def check_for_updates(self, content):
        rooms_available, status_msg, analysis = self.analyze_page_content(content)
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

        if self.last_hash is None:
            self.last_hash = content_hash
            self.last_rooms_status = rooms_available
            return rooms_available, f"İlk kontrol - {status_msg}", analysis

        content_changed = content_hash != self.last_hash
        status_changed = rooms_available != self.last_rooms_status

        self.last_hash = content_hash
        self.last_rooms_status = rooms_available

        if rooms_available and (content_changed or status_changed):
            return True, f"🚨 Daire bulundu! {status_msg}", analysis
        elif content_changed:
            return False, f"İçerik değişti ama oda yok: {status_msg}", analysis
        return False, f"Değişiklik yok: {status_msg}", analysis

    def run_monitoring(self):
        logging.info("STWDO yurt botu başlatıldı!")
        content = self.fetch_page_content()

        if content:
            should_notify, message, analysis = self.check_for_updates(content)
            if should_notify:
                alert_msg = f"""
🏠 <b>YURT ODASI BULUNDU!</b>

{message}

🔗 <a href="{self.website_url}">Hemen kontrol et ve başvur!</a>

📊 <b>Detaylar:</b>
• İlan sayısı: {analysis.get('listings_count', 0)}
• Uzunluk: {analysis.get('content_length', 0)} karakter
• Zaman: {analysis.get('timestamp')}
"""
                self.send_telegram_message(alert_msg.strip())

        while True:
            try:
                logging.info("Yeni kontrol başlatılıyor...")
                content = self.fetch_page_content()

                if content:
                    should_notify, message, analysis = self.check_for_updates(content)
                    if should_notify:
                        self.send_telegram_message(f"""
🏠 <b>YENİ ODA BULUNDU!</b>

{message}

🔗 <a href="{self.website_url}">Hemen kontrol et</a>
""")
            except Exception as e:
                logging.error(f"Döngü hatası: {e}")
            time.sleep(self.check_interval)

def start_bot():
    try:
        bot = STWDOTelegramBot()
        bot.run_monitoring()
    except Exception as e:
        logging.error(f"Bot başlatılamadı: {e}")

if __name__ == "__main__":
    flask_thread = Thread(target=lambda: app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        debug=False
    ))
    flask_thread.daemon = True
    flask_thread.start()
    time.sleep(3)
    start_bot()

