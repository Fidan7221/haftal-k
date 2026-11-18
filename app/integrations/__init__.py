"""Harici API entegrasyonları (Hafta 9).

    http.py         Ortak HTTP katmanı: zaman aşımı, yeniden deneme, hız sınırı (429), hata sınıfları
    price_api.py    Hal fiyatı API istemcisi (gerçek + sahte)
    payment_api.py  Ödeme API istemcisi (gerçek + sahte/test modu)

Servis katmanı (app/services/price_service.py, payment_service.py) bu modülleri kullanır;
rotalar hiçbir zaman doğrudan harici API çağırmaz.
"""
