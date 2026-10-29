"""Kimlik doğrulama iş mantığı (Hafta 5).

Rotalar (routes) bu fonksiyonları çağırır; veri tabanına repository üzerinden erişilir.
Kurallar:
- Kayıt formundan yalnızca "müşteri" ve "üretici" hesabı açılabilir.
- Yönetici hesabı yalnızca terminalden açılır: flask create-admin
- Parola düz metin olarak hiçbir yerde saklanmaz (User.set_password hash'ler).
- Art arda 5 hatalı girişte e-posta birkaç dakika kilitlenir (login_limiter.py).
"""
import math

from app.models import Cart, ProducerProfile, RoleName, User
from app.repositories.user_repository import RoleRepository, UserRepository
from app.services.login_limiter import get_login_limiter

SELF_REGISTER_ROLES = (RoleName.CUSTOMER, RoleName.PRODUCER)


class AuthError(Exception):
    """Kullanıcıya gösterilecek hata. field doluysa hata o form alanının altında gösterilir."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def normalize_email(email):
    return (email or "").strip().lower()


def _create_user(full_name, email, password, role_name, phone=None, city=None):
    email = normalize_email(email)

    if UserRepository.email_exists(email):
        raise AuthError("Bu e-posta adresiyle kayıtlı bir hesap zaten var.", field="email")

    role = RoleRepository.get_by_name(role_name)
    if role is None:
        raise AuthError("Roller tanımlı değil. Önce terminalde 'flask seed-db' çalıştırın.")

    user = User(
        full_name=full_name.strip(),
        email=email,
        role=role,
        phone=(phone or "").strip() or None,
        city=(city or "").strip() or None,
    )
    user.set_password(password)
    return user


def register_user(full_name, email, password, role_name,
                  phone=None, city=None, farm_name=None, region=None):
    """Yeni müşteri veya üretici kaydı oluşturur ve kullanıcıyı döndürür."""
    if role_name not in SELF_REGISTER_ROLES:
        raise AuthError("Geçersiz hesap türü.", field="role")

    user = _create_user(full_name, email, password, role_name, phone, city)

    if role_name == RoleName.PRODUCER:
        user.producer_profile = ProducerProfile(
            farm_name=farm_name.strip(), region=region.strip()
        )
    else:
        user.cart = Cart()  # Her müşterinin tek sepeti olur (Hafta 7)

    UserRepository.add(user)
    UserRepository.commit()
    return user


def create_admin_user(full_name, email, password):
    """Yalnızca CLI komutundan çağrılır."""
    user = _create_user(full_name, email, password, RoleName.ADMIN)
    UserRepository.add(user)
    UserRepository.commit()
    return user


def authenticate(email, password):
    """E-posta ve parola doğruysa kullanıcıyı, değilse None döndürür.

    Kullanıcı bulunamadığında da parolası yanlış olduğunda da aynı sonuç döner;
    böylece saldırgan hangi e-postaların kayıtlı olduğunu öğrenemez.
    """
    email = normalize_email(email)
    limiter = get_login_limiter()

    # 1) Kilitliyse parolaya hiç bakmadan reddet (kaba kuvvet denemesi durur)
    remaining = limiter.remaining_lock_seconds(email)
    if remaining > 0:
        minutes = math.ceil(remaining / 60)
        raise AuthError(
            f"Çok fazla hatalı giriş denemesi yapıldı. Lütfen {minutes} dakika sonra tekrar deneyin."
        )

    # 2) Kullanıcı yoksa da parola yanlışsa da hatalı deneme sayılır
    user = UserRepository.get_by_email(email)
    if user is None or not user.check_password(password):
        limiter.register_failure(email)
        return None

    # 3) Başarılı giriş: sayaç sıfırlanır
    limiter.reset(email)
    if not user.is_active:
        raise AuthError("Hesabınız pasif durumda. Lütfen yöneticiyle iletişime geçin.")
    return user
