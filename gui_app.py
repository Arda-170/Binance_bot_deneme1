"""
gui_app.py
----------
Forced-Flow Bot için masaüstü GUI uygulaması (Tkinter, ek kurulum gerektirmez
-- Python'ın standart kütüphanesinde gelir).

Çalıştırma:
    python gui_app.py

Not (Linux): Tkinter bazı Linux dağıtımlarında ayrı paket olabilir:
    sudo apt install python3-tk
"""

import os
import queue
import logging
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import config
from engine import BotEngine

os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(os.path.join(config.LOG_DIR, "bot.log"))],
)

# Arka plan thread'inden GUI thread'ine mesaj taşıyan kuyruk (Tkinter thread-safe değildir)
EVENT_QUEUE = queue.Queue()


class ForcedFlowApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Forced-Flow Bot — Binance Spot USDT Tarayıcı")
        self.geometry("980x640")
        self.minsize(860, 560)

        self.engine = BotEngine(
            on_log=lambda msg: EVENT_QUEUE.put(("log", msg)),
            on_scan=lambda symbol, score, breakdown, decision: EVENT_QUEUE.put(
                ("scan", symbol, score, breakdown, decision)
            ),
            on_positions=lambda positions: EVENT_QUEUE.put(("positions", positions)),
            on_status=lambda status: EVENT_QUEUE.put(("status", status)),
        )

        self._build_ui()
        self.after(200, self._poll_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- UI kurulum ----------------

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        self.start_btn = ttk.Button(top, text="▶ Botu Başlat", command=self._start_bot)
        self.start_btn.pack(side="left", padx=4)

        self.stop_btn = ttk.Button(top, text="■ Durdur", command=self._stop_bot, state="disabled")
        self.stop_btn.pack(side="left", padx=4)

        self.dry_run_var = tk.BooleanVar(value=config.DRY_RUN)
        dry_chk = ttk.Checkbutton(
            top, text="DRY_RUN (gerçek emir gönderme)",
            variable=self.dry_run_var, command=self._toggle_dry_run
        )
        dry_chk.pack(side="left", padx=16)

        self.status_label = ttk.Label(top, text="Durum: hazır", font=("TkDefaultFont", 10, "bold"))
        self.status_label.pack(side="right", padx=4)

        # ---- Ayarlar paneli ----
        settings = ttk.LabelFrame(self, text="Ayarlar (uygulamak için botu durdurup tekrar başlat)", padding=10)
        settings.pack(fill="x", padx=10, pady=(0, 6))

        self.threshold_var = tk.DoubleVar(value=config.ENTRY_SCORE_THRESHOLD)
        self.risk_var = tk.DoubleVar(value=config.RISK_PER_TRADE_PCT * 100)
        self.interval_var = tk.IntVar(value=config.SCAN_INTERVAL_SEC)

        self._labeled_spin(settings, "Giriş Skor Eşiği", self.threshold_var, 0.1, 0.95, 0.05, 0)
        self._labeled_spin(settings, "İşlem Başı Risk (%)", self.risk_var, 0.1, 10.0, 0.1, 1)
        self._labeled_spin(settings, "Tarama Aralığı (sn)", self.interval_var, 5, 300, 5, 2)

        apply_btn = ttk.Button(settings, text="Ayarları Uygula", command=self._apply_settings)
        apply_btn.grid(row=0, column=6, padx=10)

        # ---- Ana içerik: pozisyonlar + log ----
        main = ttk.Panedwindow(self, orient="vertical")
        main.pack(fill="both", expand=True, padx=10, pady=6)

        pos_frame = ttk.LabelFrame(main, text="Açık Pozisyonlar", padding=6)
        cols = ("symbol", "entry", "qty", "stop", "tp")
        self.pos_tree = ttk.Treeview(pos_frame, columns=cols, show="headings", height=6)
        headers = {"symbol": "Sembol", "entry": "Giriş", "qty": "Miktar", "stop": "Stop", "tp": "Take-Profit"}
        for c in cols:
            self.pos_tree.heading(c, text=headers[c])
            self.pos_tree.column(c, width=140, anchor="center")
        self.pos_tree.pack(fill="both", expand=True)
        main.add(pos_frame, weight=1)

        scan_frame = ttk.LabelFrame(main, text="Son Taramalar (Zorunluluk Skoru)", padding=6)
        scols = ("symbol", "score", "ob", "vol", "atr", "fund", "decision")
        self.scan_tree = ttk.Treeview(scan_frame, columns=scols, show="headings", height=8)
        sheaders = {
            "symbol": "Sembol", "score": "Toplam Skor", "ob": "OrderBook",
            "vol": "Hacim-Z", "atr": "ATR-Kırılım", "fund": "Funding/OI", "decision": "Karar",
        }
        for c in scols:
            self.scan_tree.heading(c, text=sheaders[c])
            self.scan_tree.column(c, width=110, anchor="center")
        self.scan_tree.pack(fill="both", expand=True)
        main.add(scan_frame, weight=1)

        log_frame = ttk.LabelFrame(main, text="Log", padding=6)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)
        main.add(log_frame, weight=1)

    def _labeled_spin(self, parent, label, var, frm, to, step, col):
        ttk.Label(parent, text=label).grid(row=0, column=col * 2, padx=(0, 4), pady=4, sticky="w")
        spin = ttk.Spinbox(parent, from_=frm, to=to, increment=step, textvariable=var, width=8)
        spin.grid(row=0, column=col * 2 + 1, padx=(0, 12))

    # ---------------- Buton eylemleri ----------------

    def _start_bot(self):
        if not self.engine.gw or not getattr(self.engine.gw, "has_credentials", False):
            proceed = messagebox.askokcancel(
                "API anahtarı yok",
                "Binance API anahtarı bulunamadı (.env dosyasını kontrol et).\n\n"
                "Bot yine de başlatılabilir: sadece herkese açık piyasa verisiyle "
                "tarama yapar ve DRY_RUN modunda sinyal üretir, ama GERÇEK EMİR "
                "gönderemez ve gerçek bakiye okuyamaz.\n\nDevam edilsin mi?",
            )
            if not proceed:
                return
        self.engine.start()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def _stop_bot(self):
        self.engine.stop()
        self.stop_btn.config(state="disabled")
        self.start_btn.config(state="normal")

    def _toggle_dry_run(self):
        config.DRY_RUN = self.dry_run_var.get()
        self._append_log(f"[Ayar] DRY_RUN = {config.DRY_RUN} (botu yeniden başlatınca geçerli olur)")

    def _apply_settings(self):
        config.ENTRY_SCORE_THRESHOLD = float(self.threshold_var.get())
        config.RISK_PER_TRADE_PCT = float(self.risk_var.get()) / 100.0
        config.SCAN_INTERVAL_SEC = int(self.interval_var.get())
        self._append_log(
            f"[Ayar] Eşik={config.ENTRY_SCORE_THRESHOLD:.2f} "
            f"Risk={config.RISK_PER_TRADE_PCT*100:.1f}% "
            f"Aralık={config.SCAN_INTERVAL_SEC}sn -> güncellendi"
        )

    def _on_close(self):
        if self.engine.is_running():
            self.engine.stop()
        self.destroy()

    # ---------------- Kuyruk / canlı güncelleme ----------------

    def _poll_events(self):
        try:
            while True:
                event = EVENT_QUEUE.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._append_log(event[1])
                elif kind == "scan":
                    self._append_scan(*event[1:])
                elif kind == "positions":
                    self._refresh_positions(event[1])
                elif kind == "status":
                    self._refresh_status(event[1])
        except queue.Empty:
            pass
        self.after(200, self._poll_events)

    def _append_log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _append_scan(self, symbol, score, breakdown, decision):
        if score is None:
            return  # sadece açık pozisyon kontrolüydü, tabloya eklemeye değmez
        b = breakdown or {}
        values = (
            symbol, f"{score:.3f}",
            b.get("orderbook_imbalance", ""), b.get("volume_zscore", ""),
            b.get("atr_squeeze_breakout", ""), b.get("funding_oi_bias", ""),
            decision,
        )
        self.scan_tree.insert("", 0, values=values)
        children = self.scan_tree.get_children()
        if len(children) > 200:
            self.scan_tree.delete(children[-1])

    def _refresh_positions(self, positions):
        self.pos_tree.delete(*self.pos_tree.get_children())
        for symbol, pos in positions.items():
            self.pos_tree.insert("", "end", values=(
                symbol,
                f"{pos['entry_price']:.6f}",
                f"{pos['quantity']:.6f}",
                f"{pos['stop_price']:.6f}",
                f"{pos['take_profit_price']:.6f}",
            ))

    def _refresh_status(self, status):
        mode = "DRY_RUN" if status["dry_run"] else "GERÇEK"
        cred = "API var" if status["has_credentials"] else "API yok (public)"
        text = (
            f"Durum: {'ÇALIŞIYOR' if status['running'] else 'DURDU'} | {mode} | {cred} | "
            f"Sembol: {status['cursor']}/{status['symbol_count']} | "
            f"Günlük PnL: {status['daily_pnl_pct']*100:.2f}%"
        )
        self.status_label.config(text=text)
        if not status["running"]:
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")


if __name__ == "__main__":
    app = ForcedFlowApp()
    app.mainloop()
