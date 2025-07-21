from flask import Flask
from threading import Thread
import os
import time
import logging
from datetime import datetime
import requests
import hashlib

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

# Bot sınıfını ve fonksiyonlarını burada veya başka dosyada tutabilirsin
class STWDOTelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.website_url = "https://www.stwdo.de/en/living-houses-application/current-housing-offers"
        self.check_interval = 30  # saniye
        self.last_hash = None
        self.no_results_text = "No results found for the given search criteria"
        if not self.bot_token or not self.chat_id:
            logging.error("Eksik TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID!")
            raise ValueError("Telegram ayarları eksik")

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
            logging.info("Telegram mesajı gönderildi")
            return True
        except Exception as e:
            logging.error(f"Telegram mesajı gönderilemedi: {e}")
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
            logging.error(f"Sayfa alınamadı: {e}")
            return None

    def check_for_rooms(self, content):
        if content is None:
            return False, "Sayfa içeriği alınamadı"
        has_no_results = self.no_results_text in content
        current_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        if self.last_hash is None:
            self.last_hash = current_hash
            return False, "İlk kontrol tamamlandı"
        content_changed = current_hash != self.last_hash
        self.last_hash = current_hash
        if content_changed and not has_no_results:
            return True, "🏠 ODA VAR!"
        elif content_changed:
            return False, "Sayfa değişti ama oda yok"
        else:
            return False, "Değişiklik yok"

    def run_monitoring(self):
        logging.info("Bot başladı")
        startup_msg = f"🤖 STWDO Bot başladı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        self.send_telegram_message(startup_msg)
        consecutive_errors = 0
        max_errors = 5
        while True:
            try:
                content = self.fetch_page_content()
                rooms_available, status_msg = self.check_for_rooms(content)
                if rooms_available:
                    alert_msg = "🚨 Yurt odası açıldı!"
                    self.send_telegram_message(alert_msg)
                else:
                    logging.info(status_msg)
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logging.error(f"Hata: {e}")
                if consecutive_errors >= max_errors:
                    self.send_telegram_message("⚠️ Çok fazla hata var, yeniden başlatılıyor...")
                    consecutive_errors = 0
            time.sleep(self.check_interval)

def start_bot():
    bot = STWDOTelegramBot()
    bot.run_monitoring()

if __name__ == "__main__":
    # Flask app’ı ayrı thread’de çalıştır
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000))))
    t.start()

    # Botu ana thread’de çalıştır
    start_bot()
