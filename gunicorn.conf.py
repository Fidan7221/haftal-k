"""Gunicorn ayarları (Render'daki canlı web sunucusu). Gunicorn bu dosyayı kendisi bulur.

timeout: Bir isteğe en fazla kaç saniye tanınır; süre dolunca istek öldürülür ve tarayıcı
502/503 hatası görür. Varsayılan 30 sn, yapay zekâ çağrısı için yetmiyordu: modelin zaman aşımı
30 sn ve hata olursa bir kez daha deneniyor (en kötü durumda ~60 sn). 120 sn bu süreyi karşılar.
"""
timeout = 120
