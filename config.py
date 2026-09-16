"""
config.py
---------
Tüm ayarlar burada. API anahtarlarını KESİNLİKLE koda yazma,
.env dosyasından oku (aşağıdaki gibi).

Kullanmadan önce proje klasöründe bir .env dosyası oluştur:

    BINANCE_API_KEY=xxxxxxxx
    BINANCE_API_SECRET=xxxxxxxx

.env dosyasını asla paylaşma / github'a atma.
"""

import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# ==========================================================
# GENEL MOD
# ==========================================================
DRY_RUN = True          # True: emir GÖNDERİLMEZ, sadece simüle edilir ve loglanır.
                         # Gerçek paraya geçmeden önce en az birkaç gün DRY_RUN=True ile test et.

PAPER_BALANCE_USDT = 1000.0  # API anahtarı yokken veya DRY_RUN'da kullanılan sanal bakiye

QUOTE_ASSET = "USDT"     # Sadece USDT pariteleri taranacak
EXCLUDE_SUBSTRINGS = ["UP", "DOWN", "BULL", "BEAR"]  # kaldıraçlı token'ları hariç tut

SCAN_INTERVAL_SEC = 30           # her tam tarama arası bekleme (saniye)
KLINE_INTERVAL = "5m"            # mum periyodu
KLINE_LOOKBACK = 100              # her taramada çekilecek mum sayısı
MAX_SYMBOLS_PER_SCAN = 60         # rate-limit için: tek taramada en fazla kaç sembol işlenecek (round-robin)

# ==========================================================
# SİNYAL (ZORUNLULUK SKORU) AĞIRLIKLARI
# Toplamları 1.0 olacak şekilde ayarla. Her biri -1..+1 aralığında normalize edilir.
# ==========================================================
WEIGHTS = {
    "orderbook_imbalance": 0.30,   # bid/ask hacim dengesizliği
    "volume_zscore":       0.25,   # ani hacim patlaması
    "atr_squeeze_breakout": 0.25,  # volatilite sıkışması sonrası kırılım
    "funding_oi_bias":     0.20,   # futures funding + OI sapması (opsiyonel, futures verisi çekilebilirse)
}

ENTRY_SCORE_THRESHOLD = 0.55     # bu skorun üstü LONG, altı -bu değer SHORT (spotta sadece LONG/flat)
MIN_24H_QUOTE_VOLUME = 5_000_000  # USDT cinsinden minimum günlük hacim (likidite filtresi, düşük hacimli çöp coinleri ele)

# ==========================================================
# RİSK YÖNETİMİ
# ==========================================================
MAX_OPEN_POSITIONS = 5                  # aynı anda en fazla kaç pozisyon
RISK_PER_TRADE_PCT = 0.01               # toplam bakiyenin %1'i kadar risk (stop'a kadar olan mesafeye göre boyutlanır)
MAX_ALLOCATION_PER_TRADE_PCT = 0.20     # bir işleme bakiyenin en fazla %20'si kadar sermaye ayrılır
STOP_LOSS_ATR_MULT = 1.5                # stop = giriş - 1.5*ATR
TAKE_PROFIT_ATR_MULT = 3.0              # take profit = giriş + 3*ATR  (R:R ~ 1:2)
MAX_DAILY_LOSS_PCT = 0.03               # gün içinde bakiyenin %3'ünü kaybedersen bot o gün için durur
TRAILING_STOP_ATR_MULT = 1.0            # kâra geçince iz süren stop mesafesi

# ==========================================================
# LOG
# ==========================================================
LOG_DIR = "logs"
STATE_FILE = "state.json"     # açık pozisyonlar ve günlük kayıp takibi burada tutulur
