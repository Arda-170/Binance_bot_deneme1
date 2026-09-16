"""
signals.py
----------
Burada "kim almak zorunda, kim satmak zorunda" sorusuna verilen teknik cevap var.
Dört bağımsız sinyali normalize edip ağırlıklı ortalama ile tek bir skora indiriyoruz:

  +1  -> güçlü zorunlu ALIM baskısı (short sıkışması / panik alım riski)
  -1  -> güçlü zorunlu SATIM baskısı (long likidasyonu / panik satış riski)

Not: Bu sinyaller "gelecek tahmini" değil, MEVCUT piyasa mikroyapısının
     ölçümüdür. Edge, bunları erken ve tutarlı biçimde birleştirmekten gelir;
     tek başına hiçbiri garanti değildir.
"""

import numpy as np
import pandas as pd


def klines_to_df(klines):
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ]
    df = pd.DataFrame(klines, columns=cols)
    for c in ["open", "high", "low", "close", "volume", "quote_volume",
              "taker_buy_base", "taker_buy_quote"]:
        df[c] = df[c].astype(float)
    return df


# ---------------- 1) Order book imbalance ----------------
def orderbook_imbalance(order_book, depth=20):
    """
    Bid tarafındaki toplam hacim ask tarafına göre ne kadar ağır basıyor?
    Zorunlu alıcılar (short kapatan, stop-out olan) genelde ask tarafını hızla yer;
    bunun tersi de long tarafı için geçerlidir. Sonuç -1..+1 arası.
    """
    bids = order_book.get("bids", [])[:depth]
    asks = order_book.get("asks", [])[:depth]
    bid_vol = sum(float(p) * float(q) for p, q in bids)
    ask_vol = sum(float(p) * float(q) for p, q in asks)
    total = bid_vol + ask_vol
    if total == 0:
        return 0.0
    return (bid_vol - ask_vol) / total


# ---------------- 2) Hacim z-score (anomali) ----------------
def volume_zscore(df, window=20):
    """
    Son mumun hacmi, geçmiş pencereye göre kaç standart sapma uzakta?
    Ani patlama = biriken zorunlu emirlerin piyasaya vurduğu an.
    Yön, aynı mumdaki fiyat değişimiyle belirlenir.
    """
    vol = df["volume"]
    if len(vol) < window + 1:
        return 0.0
    recent = vol.iloc[-window:-1]
    mu, sigma = recent.mean(), recent.std()
    if sigma == 0 or np.isnan(sigma):
        return 0.0
    z = (vol.iloc[-1] - mu) / sigma
    z = np.clip(z / 4.0, -1, 1)  # normalize et

    price_change = df["close"].iloc[-1] - df["open"].iloc[-1]
    direction = 1 if price_change >= 0 else -1
    return float(z * direction)


# ---------------- 3) ATR sıkışması + kırılım ----------------
def atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def atr_squeeze_breakout(df, atr_period=14, squeeze_window=20):
    """
    Volatilite (ATR) son squeeze_window periyodun en düşük %20'lik diliminde ise
    piyasa "sıkışmış" demektir -> büyük, ani (zorunlu) bir hareket genelde
    böyle sessizlik dönemlerinden sonra gelir. Kırılım yönü son mumun kapanışına göre belirlenir.
    """
    a = atr(df, atr_period)
    if a.isna().sum() > len(a) - squeeze_window:
        return 0.0
    recent_atr = a.iloc[-squeeze_window:]
    current_atr = a.iloc[-1]
    percentile = (recent_atr < current_atr).mean()  # 0 = en düşük, 1 = en yüksek

    is_squeezed = percentile < 0.35
    price_change = df["close"].iloc[-1] - df["close"].iloc[-2]
    direction = 1 if price_change >= 0 else -1

    if not is_squeezed:
        return 0.0 if abs(price_change) < a.iloc[-2] * 0.3 else 0.3 * direction

    strength = 1.0 - percentile  # sıkışma ne kadar sertse o kadar güçlü sinyal
    return float(np.clip(strength * direction, -1, 1))


# ---------------- 4) Funding / OI sapması (opsiyonel, futures verisi gerektirir) ----------------
def funding_oi_bias(funding_rate, oi_change_pct):
    """
    funding_rate > 0 ve yükseliyor  -> long'lar aşırı kalabalık -> long likidasyon riski (satım zorunluluğu) artar -> negatif skor
    funding_rate < 0 ve düşüyor      -> short'lar aşırı kalabalık -> short sıkışması riski (alım zorunluluğu) artar -> pozitif skor
    Bu veri opsiyoneldir; futures API'ye erişimin yoksa 0 döner ve o sinyal ağırlığı devre dışı kalır.
    """
    if funding_rate is None:
        return 0.0
    funding_component = -np.clip(funding_rate * 500, -1, 1)  # funding genelde çok küçük (%0.01 gibi) sayılardır
    oi_component = np.clip((oi_change_pct or 0) / 10.0, -1, 1)
    return float(np.clip(0.7 * funding_component + 0.3 * oi_component, -1, 1))


# ---------------- Toplam skor ----------------
def compute_score(df, order_book, weights, funding_rate=None, oi_change_pct=None):
    s_ob = orderbook_imbalance(order_book)
    s_vol = volume_zscore(df)
    s_atr = atr_squeeze_breakout(df)
    s_fund = funding_oi_bias(funding_rate, oi_change_pct)

    score = (
        weights["orderbook_imbalance"] * s_ob
        + weights["volume_zscore"] * s_vol
        + weights["atr_squeeze_breakout"] * s_atr
        + weights["funding_oi_bias"] * s_fund
    )
    breakdown = {
        "orderbook_imbalance": round(s_ob, 3),
        "volume_zscore": round(s_vol, 3),
        "atr_squeeze_breakout": round(s_atr, 3),
        "funding_oi_bias": round(s_fund, 3),
        "total": round(score, 3),
    }
    return score, breakdown
