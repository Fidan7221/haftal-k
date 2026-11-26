"""Ürün görseli kaydetme ve silme (Hafta 6; v0.10.4'ten itibaren veri tabanında).

Yeni yüklenen görseller veri tabanına (product_images) yazılır; ürünün image_path değeri
"db/<id>" olur. Eski sürümde diske yazılmış "products/<uuid>.jpg" yolları da okunmaya
devam eder (geriye dönük uyumluluk). "demo/..." yolları git'teki örnek görsellerdir.

Güvenlik önlemleri:
1. Dosya adı kullanıcıdan alınmaz; uuid ile rastgele ad verilir
   (aynı ad çakışması ve "../../app.py" gibi yol saldırıları önlenir).
2. Uzantı kontrolü tek başına yetmez; dosyanın ilk baytlarına (imza / magic bytes)
   bakılarak gerçekten resim olup olmadığı doğrulanır.
3. Boyut sınırı config.py içindeki MAX_CONTENT_LENGTH (5 MB) ile uygulanır.
"""
import os

from app.extensions import db
from app.models import ProductImage

PRODUCT_SUBFOLDER = "products"
DB_PREFIX = "db/"

CONTENT_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}

# Dosya türlerinin başlangıç imzaları
_SIGNATURES = {
    "png": lambda head: head.startswith(b"\x89PNG\r\n\x1a\n"),
    "jpg": lambda head: head.startswith(b"\xff\xd8\xff"),
    "jpeg": lambda head: head.startswith(b"\xff\xd8\xff"),
    "webp": lambda head: head[:4] == b"RIFF" and head[8:12] == b"WEBP",
}


def get_extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def is_real_image(file_storage):
    """Dosyanın içeriği, uzantısının söylediği resim türüyle eşleşiyor mu?"""
    check = _SIGNATURES.get(get_extension(file_storage.filename))
    if check is None:
        return False
    head = file_storage.stream.read(16)
    file_storage.stream.seek(0)  # Okuma imlecini başa al; yoksa kaydedilen dosya eksik olur
    return check(head)


def save_product_image(file_storage, upload_root=None):
    """Görseli veri tabanına ekler ve ürüne yazılacak yolu döndürür: "db/<id>".

    Commit ETMEZ: ürün kaydıyla aynı işlemde (transaction) kalıcı olur; ürün kaydı başarısız
    olursa rollback görseli de geri alır. flush() yalnızca id'yi almak için.
    """
    image = ProductImage(content_type=CONTENT_TYPES[get_extension(file_storage.filename)],
                         data=file_storage.read())
    db.session.add(image)
    db.session.flush()
    return f"{DB_PREFIX}{image.id}"


def _db_image_id(relative_path):
    if relative_path and relative_path.startswith(DB_PREFIX) and relative_path[len(DB_PREFIX):].isdigit():
        return int(relative_path[len(DB_PREFIX):])
    return None


def delete_product_image(relative_path, upload_root):
    """Görseli siler (veri tabanından ya da eski sürümde yazıldığı diskten).
    Disk yolu dışarıdan değiştirilmiş olsa bile klasör dışına çıkamaz."""
    if not relative_path:
        return
    image_id = _db_image_id(relative_path)
    if image_id is not None:
        image = db.session.get(ProductImage, image_id)
        if image is not None:
            db.session.delete(image)
            db.session.commit()
        return
    if relative_path.startswith("demo/"):
        return  # git'teki örnek görsel: silinmez
    safe_name = os.path.basename(relative_path)
    full_path = os.path.join(upload_root, PRODUCT_SUBFOLDER, safe_name)
    if os.path.isfile(full_path):
        os.remove(full_path)
