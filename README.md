# Forced-Flow Bot — Binance Spot USDT Tarayıcı (Masaüstü Uygulama)

Bu bot, Binance spot piyasasındaki **tüm USDT paritelerini** sürekli tarar ve
"zorunlu alım / zorunlu satım" baskısını yakalamaya çalışan 4 bağımsız sinyali
ağırlıklı olarak birleştirip pozisyon açar/kapatır. Artık ayrı bir pencere
olarak açılan **masaüstü GUI uygulaması** (`gui_app.py`) ile geliyor.

## Bu bot gerçekte ne yapıyor? (dürüst açıklama)

Piyasada gerçek, kanıtlanmış, kalıcı bir "sır formül" yok. Ama gerçek ve
mantıklı bir fikri (zorunlu alıcı/satıcı akışını erken yakalamak) somut,
çalışan kurallara döktüm:

| Sinyal | Neyi ölçer | "Zorunluluk" ile ilişkisi |
|---|---|---|
| Order book imbalance | Anlık bid/ask hacim dengesizliği | Bir taraf agresifçe piyasa emriyle yutuluyorsa, o taraf beklemeden almak/satmak zorunda demektir |
| Hacim z-score | Son mumun geçmişe göre anormalliği | Sessiz birikimden sonra patlama = biriken zorunlu emirlerin boşalması |
| ATR sıkışma + kırılım | Volatilitenin daralıp genişlemesi | Büyük hareketler genelde sessizlik dönemlerinden sonra, birden gelir |
| Funding/OI sapması (opsiyonel) | Vadeli işlem tarafındaki aşırı pozisyonlanma | Aşırı long/short = likidasyon zinciri riski |

## Dosya yapısı

```
config.py          -> tüm ayarlar
binance_client.py   -> Binance API sarmalayıcısı (anahtar yoksa public-only mod)
signals.py          -> 4 sinyal + toplam skor hesaplama
risk_manager.py      -> pozisyon boyutu, stop/tp, günlük kayıp limiti
executor.py          -> emir gönderme (veya DRY_RUN'da simülasyon)
engine.py            -> tarama/karar/emir döngüsü (hem CLI hem GUI bunu kullanır)
bot.py               -> terminal modu
gui_app.py           -> MASAÜSTÜ GUI (Tkinter) — asıl istediğin uygulama
```

## API anahtarı olmadan da çalışır

Gerçek bir Binance hesabın olmasa bile bot artık çökmüyor:
- API anahtarı yoksa sadece **herkese açık (public) piyasa verisiyle** tarama
  yapar, skorları hesaplar ve DRY_RUN modunda ne yapacağını gösterir.
- Sanal bakiye `config.PAPER_BALANCE_USDT` (varsayılan 1000 USDT) kullanılır.
- Gerçek hesap açtığında `.env` dosyasına anahtarları koyman yeterli,
  kodda hiçbir değişiklik gerekmez.

## Kurulum

```bash
pip install -r requirements.txt
```

Linux'ta Tkinter ayrı paket olabilir (Windows/Mac'te zaten hazırdır):
```bash
sudo apt install python3-tk
```

`.env` dosyası (opsiyonel, gerçek hesabın olduğunda doldur):
```
BINANCE_API_KEY=senin_api_keyin
BINANCE_API_SECRET=senin_api_secretin
```

API anahtarı oluştururken:
- **Sadece Spot Trading** iznini aç.
- **Withdrawal (para çekme) iznini KESİNLİKLE açma.**
- IP whitelist kullan.

## Çalıştırma

**Masaüstü uygulaması (istediğin bu):**
```bash
python gui_app.py
```
Açılan pencerede:
- **▶ Botu Başlat / ■ Durdur** butonları
- **DRY_RUN** kutucuğu (işaretliyken gerçek emir gönderilmez)
- **Ayarlar paneli**: giriş skor eşiği, işlem başı risk %, tarama aralığı —
  değiştirip "Ayarları Uygula"ya bas, sonraki başlatmada geçerli olur
- **Açık Pozisyonlar** tablosu (canlı günceller)
- **Son Taramalar** tablosu: her sembolün 4 alt-skoru + toplam skor + karar
- **Log** penceresi: tüm olaylar burada akar

**Terminal modu (istersen):**
```bash
python bot.py
```

## Ayarlanabilir parametreler (`config.py`)

- `WEIGHTS` — 4 sinyalin ağırlıkları
- `ENTRY_SCORE_THRESHOLD` — ne kadar güçlü sinyalde işleme girileceği (GUI'den de değiştirilebilir)
- `RISK_PER_TRADE_PCT`, `MAX_ALLOCATION_PER_TRADE_PCT` — pozisyon boyutu
- `STOP_LOSS_ATR_MULT`, `TAKE_PROFIT_ATR_MULT`, `TRAILING_STOP_ATR_MULT` — çıkış kuralları
- `MAX_DAILY_LOSS_PCT` — günlük kayıp devre kesici
- `MAX_OPEN_POSITIONS` — aynı anda kaç pozisyon taşınacak
- `PAPER_BALANCE_USDT` — API anahtarı yokken kullanılan sanal bakiye

## Önemli uyarılar

- Bu kod **finansal tavsiye değildir**. Gerçek para kaybı riski tamamen sana aittir.
- Gerçek hesap açtığında önce **birkaç gün DRY_RUN=True** ile izle.
- Küçük sermaye ile, düşük `RISK_PER_TRADE_PCT` ile başla.
- `MAX_SYMBOLS_PER_SCAN` değerini rate-limit'e göre ayarla.
- Vergisel ve yasal yükümlülükler tamamen sana aittir.
