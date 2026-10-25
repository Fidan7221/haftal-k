"""Uygulama fabrikası (Application Factory).

create_app() her çağrıldığında yeni bir Flask uygulaması üretir.
Testlerde farklı ayarlarla (TestingConfig) uygulama kurmayı sağlar.
"""
import os
from decimal import Decimal

import click
from flask import Flask, render_template

from config import config_by_name
from app.extensions import csrf, db, login_manager, migrate


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

    # instance/ klasörü yoksa oluştur (SQLite dosyası burada durur)
    os.makedirs(app.instance_path, exist_ok=True)

    # Eklentileri uygulamaya bağla
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)  # SQLite'ta ALTER TABLE için gerekli
    login_manager.init_app(app)
    csrf.init_app(app)

    # Modelleri içe aktar: Flask-Migrate tabloları ancak böyle görür
    from app import models  # noqa: F401

    register_blueprints(app)
    register_error_handlers(app)
    register_template_filters(app)
    register_cli_commands(app)

    return app


def register_template_filters(app):
    @app.template_filter("qty")
    def format_quantity(value):
        """Miktarı Türkçe biçimde yazar: Decimal('12.50') -> '12,5', Decimal('100.00') -> '100'"""
        if value is None:
            return "0"
        text = f"{Decimal(value).quantize(Decimal('0.01')):f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text.replace(".", ",")


def register_blueprints(app):
    from app.routes.admin_routes import admin_bp
    from app.routes.auth_routes import auth_bp
    from app.routes.main_routes import main_bp
    from app.routes.producer_routes import producer_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(producer_bp)  # Hafta 6
    app.register_blueprint(admin_bp)     # Hafta 6


def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(error):
        # MAX_CONTENT_LENGTH (5 MB) aşıldığında Flask 413 döndürür
        return render_template("errors/413.html"), 413


def register_cli_commands(app):
    """Terminalden çalıştırılacak özel komutlar."""

    @app.cli.command("seed-db")
    def seed_db():
        """Rolleri ve temel kategorileri veri tabanına ekler."""
        from scripts.seed_data import seed_all

        seed_all()
        print("Başlangıç verileri eklendi.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Ad Soyad")
    @click.option("--email", prompt="E-posta")
    @click.password_option(prompt="Parola", confirmation_prompt="Parola (tekrar)")
    def create_admin(name, email, password):
        """Yönetici hesabı oluşturur (kayıt formundan yönetici açılamaz)."""
        from app.services.auth_service import AuthError, create_admin_user

        if len(password) < 8:
            print("Hata: Parola en az 8 karakter olmalıdır.")
            return
        try:
            create_admin_user(name, email, password)
        except AuthError as error:
            print(f"Hata: {error.message}")
        else:
            print(f"Yönetici hesabı oluşturuldu: {email}")
