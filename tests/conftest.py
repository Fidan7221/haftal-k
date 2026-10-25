"""Tüm testlerin ortak hazırlıkları (pytest bu dosyayı otomatik bulur)."""
import pytest

from app import create_app
from app.extensions import db
from scripts.seed_data import seed_all


@pytest.fixture
def app(tmp_path):
    app = create_app("testing")
    # Testte yüklenen görseller gerçek static/uploads klasörünü kirletmesin
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    with app.app_context():
        db.create_all()
        seed_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# --- Ortak yardımcılar (Hafta 6) ------------------------------------------

def register_and_login(client, email, role="producer", farm_name="Test Çiftliği"):
    data = {
        "role": role,
        "full_name": "Test Kullanıcı",
        "email": email,
        "password": "Parola123",
        "confirm_password": "Parola123",
        "accept_terms": "y",
    }
    if role == "producer":
        data.update(farm_name=farm_name, region="Bingöl / Merkez")
    client.post("/auth/register", data=data)
    client.post("/auth/login", data={"email": email, "password": "Parola123"})
