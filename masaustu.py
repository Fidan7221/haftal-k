"""Masaüstü başlatıcı: uygulamayı çift tıklanınca açılan bir programa çevirir.

Çalıştırma (derlemeden önce deneme):  python masaustu.py
Derleme:                              python build_exe.py

Ne yapar?
1. Veri klasörünü hazırlar: %LOCALAPPDATA%\\TarladanSofraya\\ (veri.db, gizli_anahtar.txt, demo_parola.txt)
   Veriler .exe'nin yanında tutulmaz; program silinse/güncellense de kaybolmaz.
2. Gizli anahtarı ve demo parolasını ilk açılışta rastgele üretir ve saklar (koda veya pakete yazılmaz).
3. Tabloları oluşturur; roller, kategoriler ve demo verisini ekler (tekrar çalıştırmak güvenlidir).
4. Sunucuyu yalnızca bu bilgisayarda (127.0.0.1) boş bir portta başlatır.
5. Tarayıcıyı açar ve küçük bir kontrol penceresi gösterir. Pencere kapanınca program kapanır.
"""
import os
import secrets
import socket
import sys
import threading
import webbrowser

APP_NAME = "TarladanSofraya"
HOST = "127.0.0.1"          # 0.0.0.0 olsaydı aynı ağdaki herkes bağlanabilirdi
PORTS = range(5050, 5060)


def data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def load_or_create(folder, filename, factory, min_length):
    """Dosyadaki değeri okur; yoksa üretip kaydeder. Her bilgisayarın değeri farklıdır."""
    path = os.path.join(folder, filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            value = f.read().strip()
        if len(value) >= min_length:
            return value
    value = factory()
    with open(path, "w", encoding="utf-8") as f:
        f.write(value)
    return value


def find_free_port():
    for port in PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError("5050-5059 arasında boş port bulunamadı.")


def build_app(folder):
    # Ayarlar config.py içe aktarılmadan ÖNCE ortam değişkeni olarak verilmeli,
    # çünkü config.py değerleri sınıf tanımlanırken okur.
    os.environ["SECRET_KEY"] = load_or_create(folder, "gizli_anahtar.txt", lambda: secrets.token_hex(32), 32)
    os.environ["DEMO_PASSWORD"] = load_or_create(folder, "demo_parola.txt", lambda: "Demo-" + secrets.token_hex(4), 8)
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(folder, "veri.db").replace("\\", "/")
    os.environ["FLASK_ENV"] = "production"

    from app import create_app
    from app.extensions import db
    from scripts.demo_data import seed_demo
    from scripts.seed_data import seed_all

    app = create_app("production")
    # ProductionConfig çerezleri yalnızca HTTPS'te gönderir (Render için doğru). Masaüstünde
    # sunucu yalnızca 127.0.0.1'de HTTP ile çalışır; trafik bilgisayardan çıkmadığı için kapatılır.
    # Kapatılmazsa tarayıcı oturum çerezini geri göndermez ve giriş yapılamaz.
    app.config["SESSION_COOKIE_SECURE"] = False
    app.config["REMEMBER_COOKIE_SECURE"] = False
    # Hafta 10: AI günlüğü .exe klasörüne değil veri klasörüne yazılır (orası yazılabilir)
    app.config["AI_LOG_PATH"] = os.path.join(folder, "ai_gunlugu.jsonl")

    from app.services.price_service import sync_prices

    with app.app_context():
        db.create_all()   # tablolar yoksa oluşturur, varsa dokunmaz
        seed_all()        # roller + kategoriler (kopya eklemez)
        seed_demo()       # demo üretici/müşteri/yönetici ve ürünler (yalnızca ilk sefer)
        sync_prices(days=60)  # Hafta 9: hal fiyatları (olan günleri tekrar çekmez)
    return app


def open_browser_when_ready(port, url, timeout=30):
    """Sunucu portu bağlantı kabul edene kadar bekler, sonra tarayıcıyı açar."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.3)
    webbrowser.open(url)


def serve(app, port):
    try:
        from waitress import serve as waitress_serve
    except ImportError:  # waitress kurulu değilse Flask'ın kendi sunucusu (yalnızca yedek)
        app.run(host=HOST, port=port, debug=False, use_reloader=False)
    else:
        waitress_serve(app, host=HOST, port=port, threads=8)


DEMO_ACCOUNTS = "uretici1@example.com · musteri@example.com · yonetici@example.com"


def control_window(url, demo_password):
    """Küçük kontrol penceresi. Kapanınca program (ve sunucu) kapanır."""
    import tkinter as tk

    root = tk.Tk()
    root.title("Tarladan Sofraya")
    root.geometry("440x210")
    root.resizable(False, False)
    tk.Label(root, text="Tarladan Sofraya çalışıyor", font=("Segoe UI", 12, "bold")).pack(pady=(14, 2))
    tk.Label(root, text=url, fg="#2e7d32").pack()
    tk.Label(root, text="Demo hesaplar: " + DEMO_ACCOUNTS, fg="#555", wraplength=420).pack(pady=(8, 0))
    tk.Label(root, text="Demo parolası: " + demo_password, font=("Segoe UI", 10, "bold")).pack()
    buttons = tk.Frame(root)
    buttons.pack(pady=14)
    tk.Button(buttons, text="Tarayıcıda aç", width=14, command=lambda: webbrowser.open(url)).pack(side="left", padx=6)
    tk.Button(buttons, text="Kapat", width=10, command=root.destroy).pack(side="left", padx=6)
    root.mainloop()


def main():
    # --windowed derlemede konsol yoktur (sys.stdout = None); log yazan kütüphaneler çökmesin
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    folder = data_dir()
    app = build_app(folder)
    port = find_free_port()
    url = f"http://{HOST}:{port}/"

    # Sunucu arka planda (daemon) çalışır: ana pencere kapanınca o da kapanır
    threading.Thread(target=serve, args=(app, port), daemon=True).start()
    # Tarayıcıyı sunucu gerçekten cevap verince aç (erken açılırsa "Bu siteye ulaşılamıyor" görünür)
    threading.Thread(target=open_browser_when_ready, args=(port, url), daemon=True).start()

    try:
        control_window(url, os.environ["DEMO_PASSWORD"])
    except Exception:
        # tkinter yoksa konsol modunda çalış
        print(f"Uygulama açık: {url}\nKapatmak için Ctrl+C.")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    sys.exit(0)


def show_startup_error(error):
    """Pencereli .exe'de konsol olmadığı için başlangıç hatası ekranda ve dosyada gösterilir."""
    import traceback

    details = traceback.format_exc()
    try:
        with open(os.path.join(data_dir(), "hata.txt"), "w", encoding="utf-8") as f:
            f.write(details)
    except OSError:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Tarladan Sofraya açılamadı",
                             f"{error}\n\nAyrıntı: %LOCALAPPDATA%\\{APP_NAME}\\hata.txt")
    except Exception:
        print(details)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        show_startup_error(exc)
        sys.exit(1)
