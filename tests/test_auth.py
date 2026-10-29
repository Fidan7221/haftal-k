"""Hafta 5 testleri: kayıt, giriş, çıkış ve rol tabanlı erişim.

Çalıştırma: pytest -v tests/test_auth.py
"""
from app.models import RoleName
from app.repositories.user_repository import UserRepository

CUSTOMER = {
    "role": RoleName.CUSTOMER,
    "full_name": "Ayşe Müşteri",
    "email": "Ayse@Test.com",
    "password": "Parola123",
    "confirm_password": "Parola123",
    "accept_terms": "y",
}

PRODUCER = {
    **CUSTOMER,
    "role": RoleName.PRODUCER,
    "full_name": "Mehmet Çiftçi",
    "email": "mehmet@test.com",
    "farm_name": "Genç Organik Çiftliği",
    "region": "Bingöl / Genç",
}


def register(client, data):
    return client.post("/auth/register", data=data, follow_redirects=True)


def login(client, email, password="Parola123"):
    return client.post("/auth/login", data={"email": email, "password": password},
                       follow_redirects=True)


# --- Kayıt ---------------------------------------------------------------

def test_register_customer_creates_user_and_cart(client):
    response = register(client, CUSTOMER)
    assert "Kaydınız oluşturuldu" in response.get_data(as_text=True)

    user = UserRepository.get_by_email("ayse@test.com")  # e-posta küçük harfe çevrildi
    assert user is not None and user.is_customer
    assert user.cart is not None
    assert user.password_hash != "Parola123"  # parola hash'lendi


def test_register_producer_creates_profile(client):
    register(client, PRODUCER)
    user = UserRepository.get_by_email("mehmet@test.com")
    assert user.is_producer
    assert user.producer_profile.farm_name == "Genç Organik Çiftliği"


def test_producer_requires_farm_name(client):
    data = {**PRODUCER, "farm_name": ""}
    response = register(client, data)
    assert "çiftlik adı zorunludur" in response.get_data(as_text=True)
    assert UserRepository.get_by_email("mehmet@test.com") is None


def test_duplicate_email_rejected(client):
    register(client, CUSTOMER)
    response = register(client, CUSTOMER)
    assert "zaten var" in response.get_data(as_text=True)


def test_weak_password_rejected(client):
    data = {**CUSTOMER, "password": "sadeceharf", "confirm_password": "sadeceharf"}
    response = register(client, data)
    assert "harf ve bir rakam" in response.get_data(as_text=True)


def test_cannot_self_register_as_admin(client):
    data = {**CUSTOMER, "role": RoleName.ADMIN}
    register(client, data)
    assert UserRepository.get_by_email("ayse@test.com") is None


# --- Giriş / çıkış -------------------------------------------------------

def test_login_success_redirects_to_role_panel(client):
    register(client, PRODUCER)
    response = login(client, "mehmet@test.com")
    page = response.get_data(as_text=True)
    assert "Üretici Paneli" in page


def test_login_wrong_password(client):
    register(client, CUSTOMER)
    response = login(client, "ayse@test.com", "YanlisParola1")
    assert "E-posta veya parola hatalı" in response.get_data(as_text=True)


def test_logout_requires_post(client):
    register(client, CUSTOMER)
    login(client, "ayse@test.com")
    assert client.get("/auth/logout").status_code == 405  # GET ile çıkış yapılamaz
    response = client.post("/auth/logout", follow_redirects=True)
    assert "Oturumunuz kapatıldı" in response.get_data(as_text=True)


def test_open_redirect_blocked(client):
    register(client, CUSTOMER)
    response = client.post(
        "/auth/login?next=https://kotu-site.com",
        data={"email": "ayse@test.com", "password": "Parola123"},
    )
    assert response.status_code == 302
    assert "kotu-site.com" not in response.headers["Location"]


# --- Rol tabanlı erişim ----------------------------------------------------

def test_anonymous_redirected_to_login(client):
    response = client.get("/uretici/panel")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_customer_cannot_open_producer_panel(client):
    register(client, CUSTOMER)
    login(client, "ayse@test.com")
    assert client.get("/uretici/panel").status_code == 403


def test_producer_cannot_open_customer_panel(client):
    register(client, PRODUCER)
    login(client, "mehmet@test.com")
    assert client.get("/musteri/panel").status_code == 403


# --- Hatalı giriş sınırı (kaba kuvvete karşı) ---------------------------------

class FakeClock:
    """Testte 5 dakika beklememek için elle ileri sarılabilen saat."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def use_fake_clock():
    from app.services.login_limiter import get_login_limiter

    clock = FakeClock()
    get_login_limiter().clock = clock
    return clock


def fail_login(client, email, times):
    for _ in range(times):
        login(client, email, "YanlisParola1")


def test_account_locked_after_max_failed_attempts(client):
    register(client, CUSTOMER)
    fail_login(client, "ayse@test.com", 5)

    # Kilitliyken doğru parola da kabul edilmez
    response = login(client, "ayse@test.com")
    page = response.get_data(as_text=True)
    assert "Çok fazla hatalı giriş denemesi" in page
    assert client.get("/musteri/panel").status_code == 302  # oturum açılmadı


def test_four_failures_do_not_lock(client):
    register(client, CUSTOMER)
    fail_login(client, "ayse@test.com", 4)
    response = login(client, "ayse@test.com")
    assert "Çok fazla hatalı giriş denemesi" not in response.get_data(as_text=True)
    assert client.get("/musteri/panel").status_code == 200


def test_lock_expires_after_lockout_time(client, app):
    register(client, CUSTOMER)
    clock = use_fake_clock()
    fail_login(client, "ayse@test.com", 5)
    assert "Çok fazla hatalı" in login(client, "ayse@test.com").get_data(as_text=True)

    clock.now += app.config["LOGIN_LOCKOUT_MINUTES"] * 60 + 1  # süre doldu
    login(client, "ayse@test.com")
    assert client.get("/musteri/panel").status_code == 200


def test_successful_login_resets_counter(client):
    register(client, CUSTOMER)
    fail_login(client, "ayse@test.com", 4)
    login(client, "ayse@test.com")          # başarılı giriş sayacı sıfırlar
    client.post("/auth/logout")
    fail_login(client, "ayse@test.com", 4)  # yeniden 4 hata: toplam 8 ama kilit yok
    login(client, "ayse@test.com")
    assert client.get("/musteri/panel").status_code == 200


def test_lock_is_per_email_and_case_insensitive(client):
    register(client, CUSTOMER)
    register(client, PRODUCER)
    fail_login(client, "AYSE@test.com", 5)  # büyük harfle denense de aynı e-posta sayılır
    assert "Çok fazla hatalı" in login(client, "ayse@test.com").get_data(as_text=True)

    # Başka bir kullanıcı etkilenmez
    response = login(client, "mehmet@test.com")
    assert "Üretici Paneli" in response.get_data(as_text=True)


def test_unknown_email_gets_same_lock_message(client):
    # Kayıtlı olmayan e-posta da kilitlenir; mesaj e-postanın var olup olmadığını ele vermez
    fail_login(client, "olmayan@test.com", 5)
    response = login(client, "olmayan@test.com")
    assert "Çok fazla hatalı giriş denemesi" in response.get_data(as_text=True)
