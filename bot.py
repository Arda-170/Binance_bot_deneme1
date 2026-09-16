"""
bot.py
------
Terminal (komut satırı) modu. GUI istiyorsan gui_app.py'yi çalıştır.

Kullanım:
    python bot.py

Durdurmak için: Ctrl + C
"""

import os
import logging

import config
from engine import BotEngine

os.makedirs(config.LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(config.LOG_DIR, "bot.log")),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("bot")


def main():
    engine = BotEngine()  # loglar zaten logging üzerinden terminale/dosyaya basılıyor
    engine.start()
    try:
        while True:
            engine._thread.join(timeout=1.0)
            if not engine.is_running():
                break
    except KeyboardInterrupt:
        log.info("Kullanıcı tarafından durduruldu (Ctrl+C).")
        engine.stop()
        engine._thread.join(timeout=10.0)


if __name__ == "__main__":
    main()
