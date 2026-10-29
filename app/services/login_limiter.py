"""Hatalı giriş denemesi sınırı (Hafta 5 — kaba kuvvet saldırısına karşı).

Kural: Aynı e-posta ile art arda LOGIN_MAX_ATTEMPTS (varsayılan 5) kez hatalı giriş
yapılırsa o e-posta LOGIN_LOCKOUT_MINUTES (varsayılan 5) dakika kilitlenir.
Kilitliyken parola doğru olsa bile giriş yapılamaz. Başarılı girişte sayaç sıfırlanır.

Neden bellekte tutuyoruz?
- Ek kütüphane (Flask-Limiter, Redis) ve yeni migration gerekmez.
- Kayıtlı olmayan e-postalar için de çalışır; böylece kilit mesajı
  "bu e-posta kayıtlı mı?" sorusunu ele vermez.
Sınırı: Sunucu yeniden başlarsa sayaçlar sıfırlanır ve birden çok sunucu
işlemi (process) kullanılırsa her biri kendi sayacını tutar. Gerçek yayında
bu bilgi veri tabanında veya Redis'te tutulmalıdır.
"""
import time
from threading import Lock

from flask import current_app


class LoginAttemptLimiter:
    def __init__(self, max_attempts=5, lockout_seconds=300, clock=time.monotonic):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self.clock = clock  # Testlerde sahte saat verilebilsin diye dışarıdan alınır
        self._attempts = {}  # e-posta -> {"count": hatalı deneme sayısı, "locked_until": zaman}
        self._lock = Lock()  # Aynı anda gelen isteklerde sözlük bozulmasın

    def remaining_lock_seconds(self, key):
        """Kilit varsa kalan saniyeyi, yoksa 0 döndürür. Süresi dolan kilit silinir."""
        with self._lock:
            entry = self._attempts.get(key)
            if entry is None or entry["locked_until"] is None:
                return 0
            remaining = entry["locked_until"] - self.clock()
            if remaining <= 0:
                # Kilit süresi doldu: kullanıcı yeniden 5 deneme hakkıyla başlar
                del self._attempts[key]
                return 0
            return remaining

    def is_locked(self, key):
        return self.remaining_lock_seconds(key) > 0

    def register_failure(self, key):
        """Hatalı denemeyi sayar; sınıra ulaşıldıysa kilidi başlatır."""
        with self._lock:
            entry = self._attempts.setdefault(key, {"count": 0, "locked_until": None})
            entry["count"] += 1
            if entry["count"] >= self.max_attempts:
                entry["locked_until"] = self.clock() + self.lockout_seconds

    def reset(self, key):
        """Başarılı girişten sonra sayaç silinir."""
        with self._lock:
            self._attempts.pop(key, None)


def get_login_limiter():
    """Uygulamaya ait sınırlayıcıyı döndürür; ilk çağrıda config.py ayarlarıyla oluşturur.

    Nesne app.extensions içinde tutulur: her test yeni bir uygulama kurduğu için
    testler birbirinin sayacını etkilemez.
    """
    limiter = current_app.extensions.get("login_limiter")
    if limiter is None:
        limiter = LoginAttemptLimiter(
            max_attempts=current_app.config["LOGIN_MAX_ATTEMPTS"],
            lockout_seconds=current_app.config["LOGIN_LOCKOUT_MINUTES"] * 60,
        )
        current_app.extensions["login_limiter"] = limiter
    return limiter
