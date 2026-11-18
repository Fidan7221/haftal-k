"""Ortak HTTP katmanı (Hafta 9): bütün harici API istekleri buradan geçer.

Neden tek yer?
  Zaman aşımı, yeniden deneme ve hata çevirme kuralları her API için aynıdır.
  Her istemci bunları ayrı ayrı yazsaydı biri mutlaka unutulurdu (ör. timeout'suz istek
  sunucuyu sonsuza kadar bekletir).

Kurallar:
  - HER istekte timeout vardır.
  - Zaman aşımı, bağlantı hatası, 429 (hız sınırı) ve 5xx (sunucu hatası) GEÇİCİ hatalardır:
    biraz bekleyip en fazla `max_retries` kez yeniden denenir (üstel bekleme: 0,5 - 1 - 2 sn).
  - 429 yanıtında sunucunun "Retry-After" başlığı varsa o kadar beklenir (en fazla 5 sn).
  - 4xx (400, 401, 404 ...) KALICI hatalardır: yeniden denemek işe yaramaz, hemen hata verilir.
  - Yanıt JSON değilse ApiResponseError.

Her hata IntegrationError'dan türer. `user_message` kullanıcıya gösterilecek Türkçe ve
GÜVENLİ metindir (içinde API anahtarı, adres veya teknik ayrıntı yoktur).
"""
import logging
import time

import requests

log = logging.getLogger(__name__)

MAX_RETRY_AFTER = 5  # sunucu "60 sn bekle" dese de kullanıcıyı 5 sn'den fazla bekletmeyiz

# Testlerde gerçekten beklememek için değiştirilebilir (monkeypatch)
sleep = time.sleep


class IntegrationError(Exception):
    """Harici API ile ilgili bütün hataların atası."""

    user_message = "Dış servise şu anda ulaşılamıyor. Lütfen biraz sonra tekrar deneyin."

    def __init__(self, detail, status_code=None, user_message=None):
        super().__init__(detail)
        self.detail = detail              # günlüğe yazılır (teknik)
        self.status_code = status_code
        if user_message:
            self.user_message = user_message


class ApiTimeoutError(IntegrationError):
    user_message = "Dış servis zamanında yanıt vermedi (zaman aşımı). Lütfen tekrar deneyin."


class ApiConnectionError(IntegrationError):
    user_message = "Dış servise bağlanılamadı. İnternet bağlantısını kontrol edip tekrar deneyin."


class ApiRateLimitError(IntegrationError):
    user_message = "Dış servise çok sık istek gönderildi (hız sınırı). Bir dakika sonra tekrar deneyin."


class ApiServerError(IntegrationError):
    user_message = "Dış serviste geçici bir sorun var. Lütfen biraz sonra tekrar deneyin."


class ApiAuthError(IntegrationError):
    user_message = "Dış servis kimlik doğrulaması başarısız. Yöneticiye haber verin."


class ApiClientError(IntegrationError):
    user_message = "Dış servis isteği kabul etmedi."


class ApiResponseError(IntegrationError):
    user_message = "Dış servisten beklenmeyen bir yanıt geldi."


def _retry_after_seconds(response, attempt):
    """429 yanıtında ne kadar bekleneceği: Retry-After başlığı, yoksa üstel bekleme."""
    header = response.headers.get("Retry-After", "") if response is not None else ""
    try:
        return min(float(header), MAX_RETRY_AFTER)
    except ValueError:
        return _backoff(attempt)


def _backoff(attempt):
    return 0.5 * (2 ** attempt)  # 0,5 sn, 1 sn, 2 sn ...


def request_json(method, url, *, timeout, max_retries=2, headers=None, params=None,
                 json_body=None, data=None, session=None):
    """İsteği gönderir, JSON yanıtı sözlük olarak döndürür; olmazsa IntegrationError fırlatır.

    session: testlerde sahte oturum vermek için (varsayılan: requests modülü).
    """
    http = session or requests
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = http.request(method, url, headers=headers, params=params,
                                    json=json_body, data=data, timeout=timeout)
        except requests.Timeout:
            last_error = ApiTimeoutError(f"{method} {url}: {timeout} sn içinde yanıt yok")
            wait = _backoff(attempt)
        except requests.ConnectionError as error:
            last_error = ApiConnectionError(f"{method} {url}: bağlantı hatası ({error.__class__.__name__})")
            wait = _backoff(attempt)
        else:
            status = response.status_code
            if status == 429:
                last_error = ApiRateLimitError(f"{method} {url}: 429 hız sınırı", status)
                wait = _retry_after_seconds(response, attempt)
            elif status >= 500:
                last_error = ApiServerError(f"{method} {url}: sunucu hatası {status}", status)
                wait = _backoff(attempt)
            elif status in (401, 403):
                raise ApiAuthError(f"{method} {url}: yetki hatası {status}", status)
            elif status >= 400:
                raise ApiClientError(f"{method} {url}: istemci hatası {status}", status,
                                     user_message=_provider_message(response))
            else:
                try:
                    return response.json()
                except ValueError:
                    raise ApiResponseError(f"{method} {url}: yanıt JSON değil", status) from None

        # Buraya yalnızca GEÇİCİ hatalarda gelinir
        if attempt < max_retries:
            log.warning("Harici API geçici hata (%s), %.1f sn sonra yeniden denenecek (%d/%d)",
                        last_error.detail, wait, attempt + 1, max_retries)
            sleep(wait)

    log.error("Harici API başarısız: %s", last_error.detail)
    raise last_error


def _provider_message(response):
    """Bazı API'ler 4xx yanıtında açıklama gönderir: {"error": {"message": "..."}}."""
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"][:200]
    return None
