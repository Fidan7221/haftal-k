# Canlı Yayın (Deployment) Rehberi — Render (Hafta 7)

Sonuç: `https://tarladan-sofraya.onrender.com` gibi herkesin açabileceği bir **aktif URL**.
Render ücretsizdir; kredi kartı istemez. Kurulum yaklaşık 15 dakika sürer.

## Mimari: canlıda ne değişiyor?

| | Yerelde (VS Code) | Canlıda (Render) |
|---|---|---|
| Web sunucusu | `python run.py` (Flask geliştirme sunucusu) | `gunicorn run:app` (üretim sunucusu) |
| Veri tabanı | SQLite dosyası `instance/app.db` | PostgreSQL (Render'ın yönettiği sunucu) |
| Tabloları kim kurar? | `flask db upgrade` | Aynı komut, her açılışta otomatik |
| Ayarlar nereden gelir? | `.env` dosyası (git'e gönderilmez) | Render panelindeki **Environment** değişkenleri |
| Mod | `FLASK_ENV=development` (DEBUG açık) | `FLASK_ENV=production` (DEBUG kapalı, çerezler yalnızca HTTPS) |

Bunların hepsi repodaki **`render.yaml`** dosyasında yazılı. Render bu dosyayı okuyup her şeyi kendisi kurar.

## Ortam değişkenleri

| Değişken | Değeri | Kim belirler |
|---|---|---|
| `FLASK_APP` | `run.py` | render.yaml |
| `FLASK_ENV` | `production` | render.yaml |
| `SECRET_KEY` | Uzun rastgele metin (oturum çerezlerini imzalar) | **Render üretir** (`generateValue: true`) |
| `DATABASE_URL` | `postgresql://...` | **Render, veri tabanından otomatik bağlar** |
| `DEMO_PASSWORD` | Demo hesapların parolası (en az 8 karakter) | **Siz girersiniz** (kurulumda sorulur) |
| `PYTHON_VERSION` | `3.12.7` | render.yaml |

> Gizli bilgi (parola, anahtar) **asla koda yazılmaz**. `SECRET_KEY` eksikse uygulama canlıda bilerek açılmaz
> (`app/__init__.py`), böylece herkesin bildiği geliştirme anahtarıyla yayına çıkılmaz.

---

## Adım adım

### 1. Kodun son hâlini GitHub'a gönder (VS Code terminali)

```
cd C:\Users\fidan\OneDrive\Desktop\haftalık\satş\ciftci-platformu\ciftci-platformu
venv\Scripts\activate
python -m pytest           # 87 test geçmeli
git push
```

GitHub'da `Fidan7221/haftal-k` reposunun ana sayfasında `render.yaml` dosyasını görmelisiniz.

### 2. Render hesabı aç

1. <https://render.com> → **Get Started** → **GitHub** ile giriş yapın.
2. Render GitHub erişimi isterse **haftal-k** reposuna izin verin (Only select repositories → haftal-k).

### 3. Blueprint ile kur

1. Render panelinde sağ üstte **New +** → **Blueprint**.
2. Repo listesinden **haftal-k** → **Connect**.
3. Blueprint Name: `tarladan-sofraya`. Render, `render.yaml` dosyasını okuyup iki şey kuracağını gösterir:
   - `tarladan-sofraya` (Web Service, Free)
   - `tarladan-sofraya-db` (PostgreSQL, Free)
4. **DEMO_PASSWORD** alanı boş gelir: en az 8 karakterlik bir parola yazın (ör. `Hasat2026!`). Bunu not edin.
5. **Apply** (veya **Deploy Blueprint**).

### 4. Kurulumu izle

1. Sol menüden **tarladan-sofraya** web servisine tıklayın → **Logs**.
2. Önce `pip install` satırları akar (Build), sonra açılışta şunları görmelisiniz:
   ```
   Running upgrade  -> c612d580ebbd, ilk sema (hafta 3-7 tum tablolar)
   Başlangıç verileri eklendi.
   Demo verisi eklendi: 2 üretici, 1 müşteri.
   Listening at: http://0.0.0.0:10000
   ```
3. Üstte durum **Live** (yeşil) olunca hazırdır. İlk kurulum 5-10 dakika sürebilir.

### 5. Aktif URL'yi aç ve dene

Servis sayfasının üstündeki adres (ör. `https://tarladan-sofraya.onrender.com`; ad doluysa sonuna ek gelir).

Sunumda gösterilecek akış:

1. **Ana sayfa** ve **İlanlar**: 6 demo ilan görünür.
2. **Müşteri** ile giriş: `musteri@example.com` / DEMO_PASSWORD
   → ilan aç → **Sepete ekle** → iki farklı üreticiden ürün ekleyin → **Siparişe geç** → adres yazın
   → "2 ayrı sipariş oluşturuldu" → sipariş detayında **Öde (deneme ödemesi)**.
3. **Üretici** ile giriş: `uretici1@example.com` (veya `uretici2@example.com`) / DEMO_PASSWORD
   → **Siparişler** → ödenmiş sipariş → **Kargoya verdim**. **İlanlarım**'da stoğun düştüğünü gösterin.
4. Müşteriye dönüp **Teslim alındı**.
5. Doğrulama örneği: stoktan fazla miktar girip "Stokta yalnızca ... var" hatasını gösterin.

> Demo hesaplar uydurmadır (KVKK): `example.com` alan adı örnekler için ayrılmıştır, gerçek kişiye ait değildir.

### 6. Adresi README'ye yaz

`README.md` başındaki **Canlı adres** satırına URL'yi yazın, commit + push. (Render her push'ta otomatik yeniden kurar.)

---

## Sorun çözme

| Belirti (Logs'ta) | Sebep | Çözüm |
|---|---|---|
| Sayfa ilk açılışta 30-60 sn bekliyor | Ücretsiz servis 15 dk boşta kalınca uyur | Normal. Sunumdan birkaç dakika önce adresi bir kez açın |
| `RuntimeError: SECRET_KEY ortam değişkeni tanımlanmamış` | Değişken yok | Web servis → **Environment** → `SECRET_KEY` ekle (Generate) → Save |
| `could not translate host name` / `connection refused` | `DATABASE_URL` yanlış | Veri tabanı sayfasından **Internal Database URL**'yi kopyalayıp `DATABASE_URL`'ye yapıştırın |
| `relation "users" does not exist` | Tablolar kurulmamış | Start Command'in `flask db upgrade && ...` ile başladığını kontrol edin |
| `DEMO_PASSWORD tanımlı değil` | Değer girilmemiş | Environment → `DEMO_PASSWORD` ekle → **Manual Deploy → Deploy latest commit** |
| `ModuleNotFoundError: psycopg` | requirements eksik | `requirements.txt`'te `psycopg[binary]` satırı olmalı, push edin |
| Yüklenen ürün resimleri yeniden kurulumdan sonra kayboldu | Ücretsiz servisin diski kalıcı değil | Bilinen sınır; ileride bulut depolama (S3/Cloudinary) kullanılabilir. Veriler PostgreSQL'de olduğu için kaybolmaz |
| 30 gün sonra veri tabanı hatası | Render'ın ücretsiz PostgreSQL'i 30 günde dolar | Yeni ücretsiz veri tabanı açıp `DATABASE_URL`'yi değiştirin (veya Neon.tech gibi kalıcı ücretsiz PostgreSQL) |

## Blueprint çalışmazsa: elle kurulum

1. **New + → PostgreSQL** → Name `tarladan-sofraya-db`, Region Frankfurt, Plan Free → Create. Açılınca **Internal Database URL**'yi kopyalayın.
2. **New + → Web Service** → haftal-k reposu →
   - Runtime: Python 3, Region: Frankfurt, Plan: Free
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `flask db upgrade && flask seed-db && flask seed-demo && gunicorn run:app --bind 0.0.0.0:$PORT`
3. **Environment Variables**: `FLASK_APP=run.py`, `FLASK_ENV=production`, `SECRET_KEY` (Generate), `DATABASE_URL` (1. adımdaki adres), `DEMO_PASSWORD`, `PYTHON_VERSION=3.12.7` → **Create Web Service**.

## Bu kurulum yerelde denendi

Gönderilmeden önce aynı komutlar gerçek bir PostgreSQL 16 ve gunicorn ile çalıştırıldı:
`flask db upgrade` tabloları kurdu, `flask seed-demo` ikinci kez çalışınca hiçbir şeyi tekrar eklemedi, tarayıcıda
müşteri sepete ekleme → sipariş → ödeme ve üretici siparişi görme akışı hatasız tamamlandı.
