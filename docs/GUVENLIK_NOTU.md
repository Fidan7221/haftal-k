# Kısa Güvenlik Notu (Hafta 5 — Kullanıcı Yönetimi ve Kimlik Doğrulama)

## 1. Parola saklama
- Parola veri tabanında **düz metin olarak saklanmaz**. `User.set_password` → `werkzeug.security.generate_password_hash`
  (`app/models/user.py`). Werkzeug varsayılan olarak **scrypt** algoritmasını kullanır (bcrypt gibi yavaş ve tuzlu bir hash'tir).
- Her parolaya rastgele bir **tuz (salt)** eklenir. Aynı parolayı kullanan iki kişinin hash'i farklı çıkar; hazır
  "parola → hash" tabloları (rainbow table) işe yaramaz.
- Giriş kontrolü `check_password_hash` ile yapılır: girilen parola aynı tuzla hash'lenip karşılaştırılır.
- Parola kuralı: en az 8 karakter, güçlü parola kontrolü (`app/forms/auth_forms.py` → `strong_password`).

## 2. Oturum yönetimi
- **Oturum (session)** kullanılır (Flask-Login). Giriş sonrası kullanıcının kimliği, `SECRET_KEY` ile imzalanmış bir
  çerezde tutulur; kullanıcı çerezi değiştirirse imza bozulur ve oturum geçersiz olur.
- Çerez ayarları (`config.py`): `HttpOnly` (JavaScript okuyamaz), `SameSite=Lax` (başka siteden gelen isteğe eklenmez),
  yayında `Secure` (yalnızca HTTPS).
- **Oturum süresi:** "Beni hatırla" seçilmezse oturum tarayıcı kapanınca biter; seçilirse en fazla **7 gün** sürer.
- **Çıkış** yalnızca POST + CSRF ile yapılır; başka bir site kullanıcının oturumunu kapatamaz.
- `SECRET_KEY` koda değil `.env` dosyasına yazılır; `.env` git'e gönderilmez.

**Oturum ve token farkı:** Oturumda bilgi sunucunun imzaladığı çerezle taşınır ve tarayıcı her istekte otomatik gönderir.
Token (JWT) ise istemcinin her istekte başlığa (`Authorization: Bearer ...`) eklediği imzalı bir anahtardır; daha çok
mobil uygulama ve API'lerde kullanılır. Bu proje web arayüzü olduğu için oturum seçildi.

## 3. Rol tabanlı erişim
- Roller: **müşteri (tüketici)**, **üretici**, **yönetici**.
- `@role_required(...)` dekoratörü (`app/utils/decorators.py`) **sunucu tarafında** kontrol eder; menüde bağlantının
  gizlenmesine güvenilmez.
  - Giriş yapılmamışsa → giriş sayfasına yönlendirilir.
  - Giriş var ama rol yanlışsa → **403**.
  - Başka üreticinin ürünü → **404** (ürünün var olduğu bile belli edilmez).
- Kayıt formundan yalnızca müşteri ve üretici hesabı açılır; yönetici yalnızca terminalden (`flask create-admin`).

## 4. Diğer önlemler
- Tüm formlarda **CSRF** koruması (Flask-WTF).
- Başarısız girişte "E-posta veya parola hatalı" mesajı verilir; hangi e-postanın kayıtlı olduğu belli edilmez.
- Girişten sonra `next` adresi kontrol edilir; başka bir siteye yönlendirme (open redirect) engellenir.
- Pasif hesap giriş yapamaz.

## 4.1 Hatalı giriş denemesi sınırı (kaba kuvvet saldırısına karşı)
- Aynı e-posta ile art arda **5 hatalı giriş** yapılırsa o e-posta **5 dakika kilitlenir**
  (`config.py` → `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`).
- Kilitliyken parola **doğru olsa bile** giriş yapılamaz; "Çok fazla hatalı giriş denemesi yapıldı. Lütfen X dakika
  sonra tekrar deneyin." mesajı gösterilir. Böylece saldırgan binlerce parolayı hızlıca deneyemez.
- **Başarılı giriş** sayacı sıfırlar; kilit süresi dolunca kullanıcı yeniden 5 hakla başlar.
- E-posta küçük harfe çevrilerek sayılır (`AYSE@test.com` ile `ayse@test.com` aynı sayaçtır).
- Kayıtlı olmayan e-postalar da aynı şekilde kilitlenir; kilit mesajı "bu e-posta kayıtlı mı?" sorusunu ele vermez.
- Kod: `app/services/login_limiter.py` (`LoginAttemptLimiter`), kullanıldığı yer `auth_service.authenticate`.
- **Bilinen sınır:** Sayaç sunucu belleğinde tutulur; ek kütüphane veya migration gerekmez ama sunucu yeniden
  başlarsa sayaçlar sıfırlanır. Gerçek yayında veri tabanında veya Redis'te (ör. Flask-Limiter) tutulmalı, IP adresine
  göre de sınır konmalıdır. Ayrıca saldırgan bilerek 5 yanlış parola girerek başka birinin hesabını 5 dakika
  kilitleyebilir; kilit süresinin kısa tutulmasının nedeni budur.

## 5. Testler
`tests/test_auth.py`: kayıt, zayıf parola, aynı e-posta, yönetici olarak kayıt engeli, yanlış parola, çıkışın POST olması,
open redirect, giriş yapmamış kullanıcı ve yanlış rol erişimi.
Hatalı giriş sınırı testleri: 5 hatadan sonra kilit, 4 hatada kilit olmaması, kilit süresinin dolması (sahte saat ile),
başarılı girişin sayacı sıfırlaması, kilidin e-postaya özel ve büyük/küçük harf duyarsız olması, kayıtsız e-postada aynı mesaj.

## 6. Sözlü sınav kısa cevapları
1. **Parolayı neden hash'liyoruz, tuz nedir?** Veri tabanı çalınsa bile parolalar okunamasın diye. Tuz, parolaya eklenen
   rastgele değerdir; aynı parolalar farklı hash üretir.
2. **Oturum ve token farkı?** Yukarıda 2. bölüm.
3. **Rol tabanlı erişimi nasıl uyguladın?** `@role_required` dekoratörüyle, sunucu tarafında.
4. **Başarısız giriş denemesinde ne oluyor?** Genel bir hata mesajı gösterilir, sayfa tekrar açılır; hangi alanın yanlış
   olduğu söylenmez. Hatalı denemeler sayılır; art arda 5 hatada e-posta 5 dakika kilitlenir (4.1. bölüm).
5. **Yetkisiz kullanıcı korumalı sayfaya giderse?** Giriş yapmamışsa giriş sayfasına, rolü uymuyorsa 403 sayfasına gider.
6. **Kaba kuvvet (brute force) saldırısını nasıl engelledin?** Hatalı girişleri e-postaya göre sayıyorum; 5 hatadan sonra
   5 dakika boyunca doğru parola bile kabul edilmiyor. Sayaç başarılı girişte sıfırlanıyor.
