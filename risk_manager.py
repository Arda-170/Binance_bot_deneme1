"""
risk_manager.py
---------------
Sinyal ne kadar iyi olursa olsun, botu uzun vadede ayakta tutan şey budur.
Pozisyon boyutu, stop-loss, take-profit, günlük kayıp limiti burada yönetilir.
"""

import json
import os
import time
import math
import logging
from datetime import datetime, timezone

import config

log = logging.getLogger("risk_manager")


def _today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class RiskManager:
    def __init__(self):
        self.state = self._load_state()

    def _load_state(self):
        if os.path.exists(config.STATE_FILE):
            with open(config.STATE_FILE, "r") as f:
                return json.load(f)
        return {"date": _today_str(), "daily_pnl_pct": 0.0, "open_positions": {}}

    def _save_state(self):
        with open(config.STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def _roll_day_if_needed(self):
        if self.state.get("date") != _today_str():
            log.info("Yeni gün: günlük P&L sayaci sıfırlanıyor.")
            self.state["date"] = _today_str()
            self.state["daily_pnl_pct"] = 0.0
            self._save_state()

    # ---------------- Sınır kontrolleri ----------------

    def daily_loss_limit_hit(self):
        self._roll_day_if_needed()
        return self.state["daily_pnl_pct"] <= -abs(config.MAX_DAILY_LOSS_PCT)

    def can_open_new_position(self):
        self._roll_day_if_needed()
        if self.daily_loss_limit_hit():
            return False
        return len(self.state["open_positions"]) < config.MAX_OPEN_POSITIONS

    def has_open_position(self, symbol):
        return symbol in self.state["open_positions"]

    # ---------------- Pozisyon boyutlandırma ----------------

    def compute_position_size(self, balance_usdt, entry_price, atr_value):
        """
        Risk = bakiyenin RISK_PER_TRADE_PCT kadarı.
        Stop mesafesi = STOP_LOSS_ATR_MULT * ATR.
        qty = risk_tutari / stop_mesafesi
        Ayrıca MAX_ALLOCATION_PER_TRADE_PCT ile sermaye tavanı da uygulanır.
        """
        stop_distance = config.STOP_LOSS_ATR_MULT * atr_value
        if stop_distance <= 0:
            return 0.0

        risk_amount = balance_usdt * config.RISK_PER_TRADE_PCT
        qty_by_risk = risk_amount / stop_distance

        max_notional = balance_usdt * config.MAX_ALLOCATION_PER_TRADE_PCT
        qty_by_cap = max_notional / entry_price

        return max(0.0, min(qty_by_risk, qty_by_cap))

    @staticmethod
    def round_step_size(quantity, step_size):
        precision = int(round(-math.log(step_size, 10), 0)) if step_size < 1 else 0
        return float(f"{quantity:.{precision}f}")

    # ---------------- Pozisyon kaydı ----------------

    def register_open(self, symbol, entry_price, quantity, stop_price, take_profit_price):
        self.state["open_positions"][symbol] = {
            "entry_price": entry_price,
            "quantity": quantity,
            "stop_price": stop_price,
            "take_profit_price": take_profit_price,
            "trailing_stop": stop_price,
            "opened_at": time.time(),
        }
        self._save_state()

    def register_close(self, symbol, exit_price):
        pos = self.state["open_positions"].pop(symbol, None)
        self._save_state()
        if not pos:
            return None
        pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
        self._roll_day_if_needed()
        self.state["daily_pnl_pct"] += pnl_pct * (
            pos["entry_price"] * pos["quantity"]
        ) / max(1.0, self._current_equity_estimate())
        self._save_state()
        return pnl_pct

    def _current_equity_estimate(self):
        # basitleştirilmiş yaklaşım; gerçek uygulamada hesap bakiyesinden çekilebilir
        return config.PAPER_BALANCE_USDT

    def update_trailing_stop(self, symbol, current_price, atr_value):
        pos = self.state["open_positions"].get(symbol)
        if not pos:
            return None
        new_trail = current_price - config.TRAILING_STOP_ATR_MULT * atr_value
        if new_trail > pos["trailing_stop"]:
            pos["trailing_stop"] = new_trail
            self._save_state()
        return pos["trailing_stop"]

    def get_open_positions(self):
        return dict(self.state["open_positions"])
