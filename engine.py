"""
engine.py
---------
Botun tarama/karar/emir döngüsünün tek merkezi hali.
bot.py (terminal) ve gui_app.py (masaüstü) bu sınıfı kullanır,
böylece mantık tek yerde durur, iki kopya birbirinden sapmaz.

Kullanım:
    engine = BotEngine(on_log=..., on_scan=..., on_positions=..., on_status=...)
    engine.start()   # arka planda ayrı thread'de çalışır
    engine.stop()    # bir sonraki döngü kontrolünde durur
"""

import time
import threading
import logging

import config
import signals
from binance_client import BinanceGateway
from risk_manager import RiskManager
from executor import Executor

log = logging.getLogger("engine")


class BotEngine:
    def __init__(self, on_log=None, on_scan=None, on_positions=None, on_status=None):
        """
        on_log(text:str)
        on_scan(symbol:str, score:float, breakdown:dict, decision:str)
        on_positions(positions:dict)
        on_status(status:dict)  -> {"running", "dry_run", "symbol_count", "cursor", "daily_pnl_pct", "has_credentials"}
        """
        self.on_log = on_log or (lambda *_a: None)
        self.on_scan = on_scan or (lambda *a, **k: None)
        self.on_positions = on_positions or (lambda *a, **k: None)
        self.on_status = on_status or (lambda *a, **k: None)

        self.gw = None
        self.risk = None
        self.executor = None

        self._thread = None
        self._stop_event = threading.Event()
        self.all_symbols = []
        self.cursor = 0

    # ---------------- Yaşam döngüsü ----------------

    def _log(self, msg):
        log.info(msg)
        try:
            self.on_log(msg)
        except Exception:
            pass

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running():
            self._log("Bot zaten çalışıyor.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._log("Durdurma isteği alındı, bot bir sonraki döngüde duracak.")

    # ---------------- Ana döngü ----------------

    def _run(self):
        try:
            self.gw = BinanceGateway()
            self.risk = RiskManager()
            self.executor = Executor(self.gw, self.risk, dry_run=config.DRY_RUN)
        except Exception as e:
            self._log(f"Bot başlatılamadı: {e}")
            return

        mode = "DRY_RUN (simülasyon)" if config.DRY_RUN else "GERÇEK EMİR"
        cred = "var" if self.gw.has_credentials else "yok (sadece public veri)"
        self._log(f"Bot başladı. Mod={mode} | API anahtarı={cred}")

        try:
            self.all_symbols = self.gw.get_usdt_symbols()
        except Exception as e:
            self._log(f"Sembol listesi alınamadı: {e}")
            return

        self._log(f"{len(self.all_symbols)} adet USDT paritesi bulundu.")
        self.cursor = 0

        while not self._stop_event.is_set():
            try:
                if self.risk.daily_loss_limit_hit():
                    self._log("Günlük kayıp limiti aşıldı. Bot bugün için beklemede.")
                    self._emit_status()
                    self._wait(config.SCAN_INTERVAL_SEC)
                    continue

                ticker_map = self.gw.safe_call(self.gw.get_24h_ticker_map) or {}

                batch = self.all_symbols[self.cursor: self.cursor + config.MAX_SYMBOLS_PER_SCAN]
                if not batch:
                    self.cursor = 0
                    batch = self.all_symbols[:config.MAX_SYMBOLS_PER_SCAN]
                else:
                    self.cursor += config.MAX_SYMBOLS_PER_SCAN

                self._log(f"Tarama: {len(batch)} sembol ({self.cursor}/{len(self.all_symbols)})")
                self._emit_status()

                for symbol in batch:
                    if self._stop_event.is_set():
                        break
                    ticker = ticker_map.get(symbol)
                    if not ticker:
                        continue
                    self._scan_symbol(symbol, ticker)

                self.on_positions(self.risk.get_open_positions())
                self._wait(config.SCAN_INTERVAL_SEC)

            except Exception as e:
                self._log(f"Ana döngüde beklenmeyen hata: {e}")
                self._wait(config.SCAN_INTERVAL_SEC)

        self._log("Bot durdu.")
        self._emit_status()

    def _wait(self, seconds):
        """Uyurken de stop isteğine hızlı tepki verebilmek için küçük adımlarla bekler."""
        end = time.time() + seconds
        while time.time() < end and not self._stop_event.is_set():
            time.sleep(min(0.5, max(0.0, end - time.time())))

    def _emit_status(self):
        self.on_status({
            "running": self.is_running(),
            "dry_run": self.executor.dry_run if self.executor else config.DRY_RUN,
            "symbol_count": len(self.all_symbols),
            "cursor": self.cursor,
            "daily_pnl_pct": self.risk.state.get("daily_pnl_pct", 0.0) if self.risk else 0.0,
            "has_credentials": self.gw.has_credentials if self.gw else False,
        })

    # ---------------- Sembol tarama ----------------

    def _scan_symbol(self, symbol, ticker):
        try:
            quote_volume = float(ticker.get("quoteVolume", 0))
            if quote_volume < config.MIN_24H_QUOTE_VOLUME:
                return

            klines = self.gw.safe_call(self.gw.get_klines, symbol, config.KLINE_INTERVAL, config.KLINE_LOOKBACK)
            if not klines or len(klines) < 30:
                return
            df = signals.klines_to_df(klines)

            order_book = self.gw.safe_call(self.gw.get_order_book, symbol, 20)
            if not order_book:
                return

            atr_series = signals.atr(df)
            atr_value = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
            if atr_value <= 0:
                return

            current_price = float(df["close"].iloc[-1])

            if self.risk.has_open_position(symbol):
                self.executor.check_exit_conditions(symbol, current_price, atr_value)
                self.on_scan(symbol, None, None, "açık pozisyon kontrolü")
                return

            if not self.risk.can_open_new_position():
                return

            score, breakdown = signals.compute_score(
                df, order_book, config.WEIGHTS,
                funding_rate=None, oi_change_pct=None,
            )

            decision = "bekle"
            if score >= config.ENTRY_SCORE_THRESHOLD:
                balance = self.gw.get_account_balance("USDT")
                self._log(f"{symbol} | Skor={score:.3f} {breakdown} -> LONG sinyali")
                qty = self.executor.open_long(symbol, current_price, atr_value, balance)
                decision = "LONG açıldı" if qty else "LONG denendi (miktar 0)"

            self.on_scan(symbol, score, breakdown, decision)

        except Exception as e:
            self._log(f"{symbol} işlenirken hata: {e}")
