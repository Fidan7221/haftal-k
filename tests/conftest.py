"""Tüm testlerin ortak hazırlıkları (pytest bu dosyayı otomatik bulur)."""
import pytest

from app import create_app
from app.extensions import db
from scripts.seed_data import seed_all


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
