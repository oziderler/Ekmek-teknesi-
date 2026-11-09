# =====================================================================
# AYARLAR – Sadece bu dosyayı değiştirerek botu yönetebilirsin.
# True = açık, False = kapalı
# =====================================================================
# ---------- İZLEME LİSTESİ ----------
# Kripto: "Binance sembolü": "Yahoo yedek sembolü"
KRIPTO = {
"BTCUSDT": "BTC-USD",
"ETHUSDT": "ETH-USD",
}
# BIST hisseleri (sonuna .IS ekleme, bot kendisi ekler)
BIST = ["GZNMI", "HURGZ", "GIPTA"]
# ---------- HANGİ SEVİYELER İÇİN BİLDİRİM GELSİN ----------
HTF_SEVIYELER = True # Önceki gün / hafta / ay / yıl tepe-dip
PIVOTLAR = True # Günlük ve haftalık pivot (P, R1, S1, R2, S2)
YATAY_ALANLAR = True # Günlükte defalarca test edilmiş yatay destek/direnç
ORDER_BLOCK = True # 4S ve günlük order block (dokunulmamış olanlar)
FVG = True # 4S ve günlük doldurulmamış FVG
LIKIDITE = True # Eşit tepe/dip (EQH/EQL) + likidite süpürmesi (sweep)
YAPI = True # Market structure: BOS / CHoCH
FIBONACCI = True # Son ana dalganın 0.5 / 0.618-0.65 / 0.786 seviyeleri
# ---------- HASSASİYET ----------
TOLERANS_ATR SWING_GENISLIK = 3 MIN_DOKUNMA FIB_GUN = 0.25 # Seviyeye ne kadar yaklaşınca "geldi" sayılsın (4S ATR'nin katı)
# Tepe/dip için soldaki ve sağdaki mum sayısı
= 2 = 120 # Yatay alan sayılması için en az kaç kez test edilmiş olmalı
# Fibonacci için son kaç günün ana dalgası alınsın
# ---------- GÜNLÜK ÖZET ----------
GUNLUK_OZET_SAATI = 9 # Türkiye saatiyle her gün özet mesajı (kapatmak için: None)
