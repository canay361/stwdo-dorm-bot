from flask import Flask, jsonify
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

# Flask app
app = Flask(__name__)

@app.route("/")
def home():
    return "STWDO Bot is running!"

@app.route("/test")
def test():
    """Manuel test endpointi"""
    try:
        bot = STWDOTelegramBot()
        content = bot.fetch_page_content()
        if content:
            rooms_available, message, analysis = bot.analyze_page_content(content)

            soup = BeautifulSoup(content, 'html.parser')
            listings = soup.select('.housing-offer-item, .offer-item')
            sample_listings = [
                f"{idx+1}. {listing.get_text(' ', strip=True)[:100]}"
                for idx, listing in enumerate(listings[:5])
            ]

            return jsonify({
                "rooms_available": rooms_available,
                "message": message,
                "analysis": analysis,
                "content_length": len(content),
                "listings_count": len(listings),
                "sample_listings": sample_listings,
                "contains_no_results": bool(
                    soup.find(string=re.compile(r'no results found|keine ergebnisse', re.I))
                )
            })
        return jsonify({"error": "No content fetched"})
    except Exception as e:
        return jsonify({"error": str(e)})


class STWDOTelegramBot:
    def __init__(self):
        self.bot_token = "8121909981:AAFfxdiRFLQvz6VUn_m4ZZFbCefDGL5qj_I"
        self.chat_id = "7261690497"
        self.website_url = "https://www.stwdo.de/en/living-houses-application/current-housing-offers"
        self.check_interval = 300  # 5 dakika
        self.last_hash = None
        self.last_rooms_status = None

        logging.info("Bot başlatıldı.")

    def init_webdriver(self):
        """Yerel Chrome driver'ı başlatır (headless)"""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            driver = webdriver.Chrome(options=chrome_options)
            return driver
        except Exception as e:
            logging.error(f"Yerel WebDriver başlatılamadı: {e}")
            raise

    def send_telegram_message(self, message):
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            logging.info("Telegram mesajı gönderildi.")
        except Exception as e:
            logging.error(f"Telegram mesajı gönderilemedi: {e}")

    def fetch_page_content(self):
        try:
            driver = self.init_webdriver()
            driver.get(self.website_url)
            time.sleep(5)
            content = driver.page_source
            driver.quit()
            return content
        except Exception as e:
            logging.error(f"Sayfa içeriği alınamadı: {e}")
            return None

    def analyze_page_content(self, content):
        soup = BeautifulSoup(content, 'html.parser')
        listings = soup.select('.housing-offer-item, .offer-item')
        no_results = soup.find(string=re.compile(r'no results found|keine ergebnisse', re.I))

        analysis = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "listings_count": len(listings),
            "has_no_results_message": bool(no_results),
            "content_length": len(content)
        }

        if no_results:
            return False, "No rooms available (message detected)", analysis
        if listings:
            return True, f"Found {len(listings)} listings", analysis
        return False, "No listings detected", analysis

    def check_for_updates(self, content):
        rooms_available, message, analysis = self.analyze_page_content(content)
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

        if self.last_hash is None:
            self.last_hash = content_hash
            self.last_rooms_status = rooms_available
            return rooms_available, f"Initial check: {message}", analysis

        content_changed = content_hash != self.last_hash
        status_changed = rooms_available != self.last_rooms_status

        self.last_hash = content_hash
        self.last_rooms_status = rooms_available

        if rooms_available and (content_changed or status_changed):
            return True, f"🚨 Rooms available! {message}", analysis
        return False, message, analysis

    def run_monitoring(self):
        logging.info("STWDO yurt botu başlatıldı!")

        while True:
            logging.info("Yeni kontrol başlatılıyor...")
            content = self.fetch_page_content()
            if content:
                should_notify, message, analysis = self.check_for_updates(content)
                logging.info(f"Kontrol sonucu: {message}")
                if should_notify:
                    alert = (
                        f"🏠 <b>Yeni Yurt İlanı!</b>\n\n"
                        f"{message}\n\n"
                        f"<a href=\"{self.website_url}\">Siteye Git</a>\n\n"
                        f"🕒 {analysis['timestamp']}"
                    )
                    self.send_telegram_message(alert)
            else:
                logging.warning("Sayfa içeriği alınamadı.")
            time.sleep(self.check_interval)


def start_bot():
    try:
        bot = STWDOTelegramBot()
        bot.run_monitoring()
    except Exception as e:
        logging.error(f"Bot çalıştırılamadı: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    flask_thread = Thread(target=lambda: app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        debug=False
    ))
    flask_thread.daemon = True
    flask_thread.start()

    time.sleep(2)
    start_bot()
