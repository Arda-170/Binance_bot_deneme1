"""
binance_client.py
------------------
Binance Spot API ile tüm iletişimin geçtiği tek nokta.
Böylece test/gerçek mod geçişi ve hata yönetimi tek yerden yapılır.
"""

import time
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

import config

log = logging.getLogger("binance_client")


class BinanceGateway:
    def __init__(self):
        self.has_credentials = bool(config.API_KEY and config.API_SECRET)
        if not self.has_credentials:
            log.warning(
                "BINANCE_API_KEY / BINANCE_API_SECRET bulunamadı. "
                "Sadece herkese açık (public) piyasa verisiyle çalışılacak: "
                "tarama ve DRY_RUN sinyalleri çalışır, ama gerçek emir GÖNDERİLEMEZ "
                "ve gerçek hesap bakiyesi okunamaz (sanal bakiye kullanılacak)."
            )
            # python-binance public uçlar için (klines, order book, exchange info,
            # ticker) API anahtarı olmadan da çalışır.
            self.client = Client()
        else:
            self.client = Client(config.API_KEY, config.API_SECRET)

    # ---------------- Piyasa verisi ----------------

    def get_usdt_symbols(self):
        """Aktif, USDT ile işlem gören, kaldıraçlı olmayan tüm spot pariteleri döndürür."""
        info = self.client.get_exchange_info()
        symbols = []
        for s in info["symbols"]:
            if (
                s["status"] == "TRADING"
                and s["quoteAsset"] == config.QUOTE_ASSET
                and s["isSpotTradingAllowed"]
                and not any(x in s["baseAsset"] for x in config.EXCLUDE_SUBSTRINGS)
            ):
                symbols.append(s["symbol"])
        return symbols

    def get_24h_ticker_map(self):
        """Tüm semboller için 24s istatistiklerini tek çağrıda alır -> {symbol: dict}"""
        data = self.client.get_ticker()
        return {d["symbol"]: d for d in data}

    def get_klines(self, symbol, interval, limit):
        return self.client.get_klines(symbol=symbol, interval=interval, limit=limit)

    def get_order_book(self, symbol, limit=50):
        return self.client.get_order_book(symbol=symbol, limit=limit)

    def get_account_balance(self, asset="USDT"):
        if not self.has_credentials:
            # API anahtarı yok -> gerçek hesap sorgulanamaz, sanal bakiye kullan.
            return config.PAPER_BALANCE_USDT
        bal = self.client.get_asset_balance(asset=asset)
        return float(bal["free"]) if bal else 0.0

    def get_symbol_filters(self, symbol):
        """LOT_SIZE, MIN_NOTIONAL gibi filtreleri döndürür (emir doğrulaması için gerekli)."""
        info = self.client.get_symbol_info(symbol)
        filters = {f["filterType"]: f for f in info["filters"]}
        return filters

    # ---------------- Emir işlemleri ----------------

    def place_market_buy(self, symbol, quantity):
        if not self.has_credentials:
            log.error(
                f"BUY denendi ama API anahtarı yok: {symbol}. "
                "Gerçek emir gönderilemez, DRY_RUN dışında çalıştırma."
            )
            return None
        try:
            order = self.client.order_market_buy(symbol=symbol, quantity=quantity)
            log.info(f"BUY gönderildi: {symbol} qty={quantity} -> {order['status']}")
            return order
        except (BinanceAPIException, BinanceOrderException) as e:
            log.error(f"BUY hatası {symbol}: {e}")
            return None

    def place_market_sell(self, symbol, quantity):
        if not self.has_credentials:
            log.error(
                f"SELL denendi ama API anahtarı yok: {symbol}. "
                "Gerçek emir gönderilemez, DRY_RUN dışında çalıştırma."
            )
            return None
        try:
            order = self.client.order_market_sell(symbol=symbol, quantity=quantity)
            log.info(f"SELL gönderildi: {symbol} qty={quantity} -> {order['status']}")
            return order
        except (BinanceAPIException, BinanceOrderException) as e:
            log.error(f"SELL hatası {symbol}: {e}")
            return None

    def safe_call(self, fn, *args, retries=3, backoff=2, **kwargs):
        """Rate-limit / geçici ağ hatalarına karşı tekrar deneme sarmalayıcısı."""
        for attempt in range(retries):
            try:
                return fn(*args, **kwargs)
            except BinanceAPIException as e:
                log.warning(f"API hatası (deneme {attempt+1}/{retries}): {e}")
                time.sleep(backoff * (attempt + 1))
        return None
