"""
Ekmek Teknesi – Backtest

Soru: Fiyat bir seviyeye geldiğinde, o seviye geçmişte gerçekten işe yaradı mı?

Yöntem (geleceği görmeden, mum mum ilerler):
  - Her 4S mumun kapanışında bot'un aynı hesabı yapılır (sadece o ana kadarki veriyle).
  - Fiyat mevcut bir bölgeye YENİ girdiyse bir "işlem" açılır:
        yukarıdan gelmişse -> LONG (destek testi), aşağıdan gelmişse -> SHORT (direnç testi)
        BOS/CHoCH -> kırılım yönünde, likidite sweep -> ters yönde
  - Stop = 1 x 4S ATR, hedef = 1,5 x 4S ATR, süre sınırı = 18 mum. İkisi aynı mumda olursa stop sayılır.
  - Komisyon/kayma düşülür. Sonuç R cinsindendir (1R = stop mesafesi).
  - "Edge" = işlemin R'si - aynı sembolde, rastgele bir mumda aynı yönde işlem açmanın ortalama R'si.
    Yani seviyenin rastgele girişten NE KADAR iyi olduğunu ölçer.
"""
import html
import os
import re
import sys
import time

import numpy as np
import pandas as pd

import ayarlar as A
import bot

YIL_KRIPTO = 3.0          # kripto için kaç yıl test edilsin
HORIZON = 18              # en fazla kaç 4S mum beklensin
STOP_ATR = 1.0
HEDEF_ATR = 1.5
KOMISYON = {"kripto": 0.0010, "bist": 0.0020}   # gidiş-dönüş toplam (yüzde olarak 0.10% / 0.20%)
BASLANGIC = 200           # ilk kaç mum ısınma için atlansın
MIN_ISLEM = 30            # bundan az işlemli sonuçlar "yetersiz veri"


# =====================================================================
#  VERİ
# =====================================================================
def _mum_df(satirlar):
    df = pd.DataFrame([r[:6] for r in satirlar], columns=["t", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
    return df.astype(float)


def binance_tarih(sembol, aralik, bas):
    bas_ms = int(bas.timestamp() * 1000)
    tum = []
    while True:
        d = None
        for taban in ("https://data-api.binance.vision", "https://api.binance.com"):
            d = bot._istek(f"{taban}/api/v3/klines",
                           {"symbol": sembol, "interval": aralik, "startTime": bas_ms, "limit": 1000})
            if d is not None:
                break
        if d is None:
            return None if not tum else _mum_df(tum)
        tum += d
        if len(d) < 1000:
            break
        bas_ms = int(d[-1][0]) + 1
    return _mum_df(tum) if tum else None


def tarih_al(piyasa, sembol, ysembol):
    if piyasa == "kripto":
        simdi = pd.Timestamp.now(tz="UTC")
        h4 = binance_tarih(sembol, "4h", simdi - pd.Timedelta(days=int(365 * YIL_KRIPTO + 60)))
        d1 = binance_tarih(sembol, "1d", simdi - pd.Timedelta(days=365 * 6))
        if h4 is None or d1 is None:
            return None
        return h4.iloc[:-1], d1.iloc[:-1]

    h1, d1 = bot.yahoo_mum(ysembol, "1h", "2y"), bot.yahoo_mum(ysembol, "1d", "10y")
    if h1 is None or d1 is None:
        return None
    h4 = h1.resample("4h", offset="7h").agg(bot.OHLC).dropna()
    gun = d1.index.tz_convert("Europe/Istanbul").strftime("%Y-%m-%d")
    d1.index = pd.to_datetime(gun).tz_localize("UTC")
    d1 = d1[~d1.index.duplicated(keep="last")]
    return h4.iloc[:-1], d1.iloc[:-1]


# =====================================================================
#  İŞLEM SİMÜLASYONU
# =====================================================================
def kategori(ad):
    ad = re.sub(r"\s*\(.*?\)", "", ad)
    ad = ad.replace("Bullish ", "").replace("Bearish ", "")
    if ad.startswith("Önceki"):
        return ad.replace(" Tepesi", " Tepe/Dip").replace(" Dibi", " Tepe/Dip")
    if "Pivot" in ad:
        return ad.rsplit(" ", 1)[0]
    if ad.startswith("Yatay"):
        return "Yatay Alan"
    if ad.startswith("Eşit Tepeler"):
        return "Eşit Tepeler (EQH)"
    if ad.startswith("Eşit Dipler"):
        return "Eşit Dipler (EQL)"
    if ad.startswith("Fib Golden"):
        return "Fib Golden Pocket"
    if ad.startswith("Fib 0.5"):
        return "Fib 0.5"
    if ad.startswith("Fib 0.786"):
        return "Fib 0.786"
    return ad


def sonuc(i, yon, giris, a, h, l, c, kom):
    """i. mumun kapanışında yon (+1 long / -1 short) işlemi açılırsa R sonucu."""
    stop = giris - yon * STOP_ATR * a
    hedef = giris + yon * HEDEF_ATR * a
    r = None
    for j in range(i + 1, i + HORIZON + 1):
        if yon == 1:
            if l[j] <= stop:
                r = -1.0
                break
            if h[j] >= hedef:
                r = HEDEF_ATR / STOP_ATR
                break
        else:
            if h[j] >= stop:
                r = -1.0
                break
            if l[j] <= hedef:
                r = HEDEF_ATR / STOP_ATR
                break
    if r is None:
        r = yon * (c[i + HORIZON] - giris) / (STOP_ATR * a)
    return r - kom * giris / (STOP_ATR * a)


def test_et(piyasa, sembol, h4, d1):
    h, l, c = h4.high.values, h4.low.values, h4.close.values
    n = len(h4)
    kom = KOMISYON[piyasa]
    eski_icerde, eski_anahtarlar, gorulen = set(), set(), set()
    islemler, taban_l, taban_s = [], [], []
    hata = 0
    son = n - HORIZON - 1

    for i in range(BASLANGIC, son):
        simdi = h4.index[i] + pd.Timedelta("4h")
        try:
            an = bot.analiz_et(h4.iloc[max(0, i - 499):i + 1], d1.loc[:simdi].iloc[-1200:], piyasa, simdi)
        except Exception:
            hata += 1
            continue
        fiyat, onceki, tol = c[i], c[i - 1], an["tol"]
        a = tol / A.TOLERANS_ATR
        if a <= 0 or not np.isfinite(a):
            continue

        taban_l.append(sonuc(i, 1, fiyat, a, h, l, c, kom))
        taban_s.append(sonuc(i, -1, fiyat, a, h, l, c, kom))

        icerde, anahtarlar, girisler = set(), set(), []
        for s in an["seviyeler"]:
            k = s["key"]
            anahtarlar.add(k)
            if s["lo"] - tol <= fiyat <= s["hi"] + tol:
                icerde.add(k)
                if k not in eski_icerde and k in eski_anahtarlar:
                    if onceki > s["hi"]:
                        girisler.append((kategori(s["ad"]), 1, "destek testi"))
                    elif onceki < s["lo"]:
                        girisler.append((kategori(s["ad"]), -1, "direnç testi"))
            elif k in eski_icerde and s["lo"] - 2 * tol <= fiyat <= s["hi"] + 2 * tol:
                icerde.add(k)
        eski_icerde, eski_anahtarlar = icerde, anahtarlar

        for o in an["olaylar"]:
            if o["key"] in gorulen or "yon" not in o:
                continue
            gorulen.add(o["key"])
            girisler.append((o["tip"], o["yon"], "olay"))

        for yon in (1, -1):
            ayni = [g for g in girisler if g[1] == yon]
            for kat, _, tur in ayni:
                islemler.append({"piyasa": piyasa, "sembol": sembol, "zaman": h4.index[i],
                                 "kategori": kat, "yon": yon, "tur": tur, "n_zone": len(ayni),
                                 "R": sonuc(i, yon, fiyat, a, h, l, c, kom)})

    if hata:
        print(f"  ({hata} adımda hesaplama atlandı)")
    taban = {1: float(np.mean(taban_l)) if taban_l else 0.0,
             -1: float(np.mean(taban_s)) if taban_s else 0.0}
    return pd.DataFrame(islemler), taban, len(taban_l)


# =====================================================================
#  RAPOR
# =====================================================================
def ozet(df, grup):
    satirlar = []
    medyan = df["zaman"].median()
    for ad, g in df.groupby(grup):
        n = len(g)
        e = g["edge"]
        t = e.mean() / (e.std(ddof=1) / np.sqrt(n)) if n > 2 and e.std(ddof=1) > 0 else 0.0
        satirlar.append({"ad": ad if isinstance(ad, str) else str(ad), "n": n,
                         "kazanc": (g["R"] > 0).mean() * 100, "ortR": g["R"].mean(),
                         "edge": e.mean(), "t": t,
                         "ilk": g.loc[g["zaman"] <= medyan, "edge"].mean(),
                         "son": g.loc[g["zaman"] > medyan, "edge"].mean()})
    return pd.DataFrame(satirlar).sort_values("edge", ascending=False)


def yorum(r):
    if r["n"] < MIN_ISLEM:
        return "yetersiz veri"
    if r["t"] >= 3 and r["ilk"] > 0 and r["son"] > 0:
        return "TUTARLI +"
    if r["t"] >= 2 and r["ilk"] > 0 and r["son"] > 0:
        return "olası + (şans olabilir)"
    if r["t"] <= -3 and r["ilk"] < 0 and r["son"] < 0:
        return "tutarlı eksi"
    if r["edge"] > 0:
        return "zayıf +"
    return "zayıf -"


def tablo_md(o):
    s = "| Seviye / olay | İşlem | Kazanç % | Ort. R | Edge | t | 1.yarı | 2.yarı | Yorum |\n|---|---|---|---|---|---|---|---|---|\n"
    for _, r in o.iterrows():
        s += (f"| {r['ad']} | {r['n']} | {r['kazanc']:.0f} | {r['ortR']:+.2f} | {r['edge']:+.2f} | "
              f"{r['t']:+.1f} | {r['ilk']:+.2f} | {r['son']:+.2f} | {yorum(r)} |\n")
    return s


def tablo_tg(o, adet=6):
    uygun = o[o["n"] >= MIN_ISLEM]
    secim = pd.concat([uygun.head(adet), uygun.tail(3)]).drop_duplicates("ad")
    satir = [f"{'Seviye':<22}{'n':>5}{'Kaz%':>5}{'Edge':>6}{'t':>5}"]
    for _, r in secim.iterrows():
        satir.append(f"{r['ad'][:21]:<22}{r['n']:>5}{r['kazanc']:>5.0f}{r['edge']:>+6.2f}{r['t']:>+5.1f}")
    return "\n".join(satir)


def main():
    t0 = time.time()
    semboller = [("kripto", s, y) for s, y in A.KRIPTO.items()] + [("bist", s, f"{s}.IS") for s in A.BIST]
    tum, hatalar, bilgi = [], [], []

    for piyasa, sembol, ys in semboller:
        veri = tarih_al(piyasa, sembol, ys)
        if veri is None or len(veri[0]) < BASLANGIC + HORIZON + 50:
            print(f"{sembol}: veri alınamadı / yetersiz")
            hatalar.append(sembol)
            continue
        h4, d1 = veri
        print(f"{sembol}: {len(h4)} adet 4S mum ({h4.index[0].date()} → {h4.index[-1].date()}), test başladı...", flush=True)
        df, taban, adim = test_et(piyasa, sembol, h4, d1)
        if df.empty:
            hatalar.append(sembol)
            continue
        df["edge"] = df["R"] - df["yon"].map(taban)
        tum.append(df)
        bilgi.append(f"{sembol}: {adim} adım, {len(df)} işlem, rastgele giriş ort. R: "
                     f"long {taban[1]:+.2f} / short {taban[-1]:+.2f}")
        print("  " + bilgi[-1], f"({time.time() - t0:.0f} sn)", flush=True)

    if not tum:
        bot.gonder("⚠️ Backtest: hiçbir sembolün verisi alınamadı.")
        sys.exit("Veri yok")

    hepsi = pd.concat(tum, ignore_index=True)
    hepsi.to_csv("backtest_islemler.csv", index=False)

    md = ["# Backtest sonuçları\n",
          f"Parametreler: stop {STOP_ATR} ATR, hedef {HEDEF_ATR} ATR, süre {HORIZON} mum (4S), "
          f"komisyon kripto %{KOMISYON['kripto'] * 100:.2f} / BIST %{KOMISYON['bist'] * 100:.2f}\n",
          "Okuma rehberi: **Edge** = seviyedeki işlemin R'si − rastgele girişin R'si (pozitifse seviye rastgeleden iyi). "
          "**t** ≥ 3 ve iki yarıda da pozitif ise 'TUTARLI +' denir; 2–3 arası şans olabilir. **1.yarı/2.yarı** = test süresinin iki yarısındaki edge; ikisi de pozitifse tutarlı. "
          "Çok kategori test edildiği için şans eseri t ≥ 2 çıkabilir; tek başına karar verdirmesin. "
          "Aynı anda açılan işlemler birbiriyle ilişkilidir, gerçek bağımsız örnek sayısı 'İşlem' sütunundan azdır.\n",
          "```\n" + "\n".join(bilgi) + "\n```\n"]
    mesajlar = []

    for piyasa in ("kripto", "bist"):
        d = hepsi[hepsi["piyasa"] == piyasa]
        if d.empty:
            continue
        o = ozet(d, "kategori")
        md.append(f"\n## {piyasa.upper()} – seviye türüne göre ({d['sembol'].nunique()} sembol, {len(d)} işlem)\n")
        md.append(tablo_md(o))
        mesajlar.append(f"📈 <b>{piyasa.upper()}</b> – {len(d)} işlem\n<pre>{html.escape(tablo_tg(o))}</pre>")

        d2 = d.copy()
        d2["cakisma"] = d2["n_zone"].clip(upper=3).map({1: "1 seviye", 2: "2 seviye", 3: "3+ seviye"})
        md.append(f"\n### {piyasa.upper()} – aynı anda kaç seviye çakıştı?\n")
        md.append(tablo_md(ozet(d2, "cakisma").sort_values("ad")))

        md.append(f"\n### {piyasa.upper()} – sembole göre (tüm seviyeler)\n")
        md.append(tablo_md(ozet(d, "sembol")))

        md.append(f"\n### {piyasa.upper()} – yöne göre\n")
        d3 = d.copy()
        d3["yonad"] = d3["yon"].map({1: "LONG", -1: "SHORT"})
        md.append(tablo_md(ozet(d3, "yonad")))

    rapor = "\n".join(md)
    with open("backtest_rapor.md", "w", encoding="utf-8") as f:
        f.write(rapor)
    ozet_yol = os.getenv("GITHUB_STEP_SUMMARY")
    if ozet_yol:
        with open(ozet_yol, "a", encoding="utf-8") as f:
            f.write(rapor)

    baslik = (f"🧪 <b>Backtest bitti</b> ({(time.time() - t0) / 60:.0f} dk)\n"
              "Edge: seviyenin rastgele girişe göre kazancı (R). t≥2 anlamlı. Detay: GitHub → Actions → çalışma → Summary")
    bot.gonder(baslik)
    for m in mesajlar:
        bot.gonder(m)
    if hatalar:
        bot.gonder(f"⚠️ Veri alınamayan semboller: {', '.join(hatalar)}")
    print(f"Bitti: {time.time() - t0:.0f} sn")


if __name__ == "__main__":
    main()
