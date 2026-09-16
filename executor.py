"""
executor.py
-----------
Sinyal + risk kararını gerçek (veya simüle) emre çevirir.
"""

import logging
import config

log = logging.getLogger("executor")


class Executor:
    def __init__(self, gateway, risk_manager, dry_run=True):
        self.gw = gateway
        self.risk = risk_manager
        self.dry_run = dry_run

    def _get_lot_step(self, symbol):
        filters = self.gw.get_symbol_filters(symbol)
        lot = filters.get("LOT_SIZE", {})
        return float(lot.get("stepSize", "0.00000001"))

    def open_long(self, symbol, price, atr_value, balance_usdt):
        qty = self.risk.compute_position_size(balance_usdt, price, atr_value)
        if qty <= 0:
            log.info(f"{symbol}: hesaplanan miktar 0, işlem atlandı.")
            return None

        step = self._get_lot_step(symbol)
        qty = self.risk.round_step_size(qty, step)
        if qty <= 0:
            return None

        stop_price = price - config.STOP_LOSS_ATR_MULT * atr_value
        tp_price = price + config.TAKE_PROFIT_ATR_MULT * atr_value

        if self.dry_run:
            log.info(
                f"[DRY_RUN] BUY {symbol} qty={qty} @ ~{price:.6f} "
                f"stop={stop_price:.6f} tp={tp_price:.6f}"
            )
        else:
            order = self.gw.place_market_buy(symbol, qty)
            if order is None:
                return None

        self.risk.register_open(symbol, price, qty, stop_price, tp_price)
        return qty

    def close_position(self, symbol, price, reason=""):
        positions = self.risk.get_open_positions()
        pos = positions.get(symbol)
        if not pos:
            return None

        qty = pos["quantity"]
        if self.dry_run:
            log.info(f"[DRY_RUN] SELL {symbol} qty={qty} @ ~{price:.6f} ({reason})")
        else:
            order = self.gw.place_market_sell(symbol, qty)
            if order is None:
                return None

        pnl_pct = self.risk.register_close(symbol, price)
        log.info(f"{symbol} kapatıldı. Sebep={reason} PnL%={pnl_pct*100:.2f}")
        return pnl_pct

    def check_exit_conditions(self, symbol, current_price, atr_value):
        """Her taramada açık pozisyonlar için stop / trailing stop / take-profit kontrolü."""
        positions = self.risk.get_open_positions()
        pos = positions.get(symbol)
        if not pos:
            return

        trailing = self.risk.update_trailing_stop(symbol, current_price, atr_value)

        if current_price <= pos["stop_price"]:
            self.close_position(symbol, current_price, reason="stop-loss")
        elif current_price >= pos["take_profit_price"]:
            self.close_position(symbol, current_price, reason="take-profit")
        elif trailing is not None and current_price <= trailing and current_price > pos["entry_price"]:
            self.close_position(symbol, current_price, reason="trailing-stop")
