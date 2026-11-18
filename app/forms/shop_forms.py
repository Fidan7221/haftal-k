"""İlan, sepet, ödeme ve sipariş formları (Hafta 7).

Formdaki doğrulama kullanıcıya hızlı geri bildirim içindir. Asıl iş kuralları
servis katmanında TEKRAR kontrol edilir; çünkü form atlanabilir (ör. biri doğrudan
POST isteği gönderebilir).
"""
from datetime import date

from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional, ValidationError


class ListingForm(FlaskForm):
    # Seçenekler rotada üreticinin kendi ürünleriyle doldurulur
    product_id = SelectField("Ürün", coerce=int, validators=[DataRequired(message="Ürün seçin.")])
    title = StringField("İlan başlığı", validators=[Optional(), Length(max=150)])
    price = DecimalField("Birim fiyatı (TL)", places=2, validators=[
        InputRequired(message="Fiyat girin."),
        NumberRange(min=0.01, message="Fiyat sıfırdan büyük olmalı."),
    ])
    stock_quantity = DecimalField("Satışa ayrılan miktar", places=2, validators=[
        InputRequired(message="Miktar girin."),
        NumberRange(min=0.01, message="Miktar sıfırdan büyük olmalı."),
    ])
    min_order_quantity = DecimalField("En az sipariş miktarı", places=2, default=1, validators=[
        InputRequired(message="En az sipariş miktarı girin."),
        NumberRange(min=0.01, message="Sıfırdan büyük olmalı."),
    ])
    end_date = DateField("Bitiş tarihi (isteğe bağlı)", validators=[Optional()])
    submit = SubmitField("İlanı Kaydet")


class AddToCartForm(FlaskForm):
    quantity = DecimalField("Miktar", places=2, validators=[
        InputRequired(message="Miktar girin."),
        NumberRange(min=0.01, message="Miktar sıfırdan büyük olmalı."),
    ])
    submit = SubmitField("Sepete Ekle")


class CartItemForm(FlaskForm):
    """Sepette miktar güncelleme. 0 girilirse kalem silinir."""

    quantity = DecimalField("Miktar", places=2, validators=[
        InputRequired(message="Miktar girin."),
        NumberRange(min=0, message="Miktar negatif olamaz."),
    ])
    submit = SubmitField("Güncelle")


class CheckoutForm(FlaskForm):
    shipping_address = TextAreaField("Teslimat adresi", validators=[
        DataRequired(message="Teslimat adresi zorunludur."),
        Length(min=10, max=255, message="Adres 10-255 karakter olmalı."),
    ])
    note = StringField("Üreticiye not (isteğe bağlı)", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Siparişi Oluştur")


class OrderStatusForm(FlaskForm):
    """Sipariş durum düğmeleri. Hangi durumun seçilebileceğine servis karar verir."""

    new_status = HiddenField(validators=[DataRequired()])
    submit = SubmitField("Uygula")


class ActionForm(FlaskForm):
    """İlan kapat/aç/sil ve sepetten çıkar düğmeleri: yalnızca CSRF anahtarı taşır."""

    submit = SubmitField("Uygula")


# --- Hafta 9: Ödeme formu -------------------------------------------------------------

def luhn_valid(number):
    """Kart numarasının son hanesi kontrol hanesidir (Luhn algoritması).

    Sağdan başlayarak her ikinci hane 2 ile çarpılır (9'dan büyükse 9 çıkarılır),
    hepsi toplanır; toplam 10'a tam bölünüyorsa numara geçerlidir.
    Yanlış yazılmış numarayı API'ye hiç göndermeden yakalar.
    """
    total = 0
    for index, char in enumerate(reversed(number)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _digits(text):
    return "".join(ch for ch in (text or "") if ch.isdigit())


class PaymentForm(FlaskForm):
    """Kart bilgisi. Bu bilgiler veri tabanına YAZILMAZ, yalnızca ödeme servisine iletilir."""

    card_holder = StringField("Kart üzerindeki ad", validators=[
        DataRequired(message="Kart sahibinin adını yazın."), Length(min=3, max=60)])
    card_number = StringField("Kart numarası", validators=[DataRequired(message="Kart numarasını yazın.")])
    expiry = StringField("Son kullanma (AA/YY)", validators=[DataRequired(message="Son kullanma tarihini yazın.")])
    cvc = StringField("CVC", validators=[DataRequired(message="CVC kodunu yazın.")])
    submit = SubmitField("Ödemeyi Tamamla")

    def validate_card_number(self, field):
        number = _digits(field.data)
        if not 13 <= len(number) <= 19 or not luhn_valid(number):
            raise ValidationError("Kart numarası geçersiz.")

    def validate_expiry(self, field):
        parts = (field.data or "").replace(" ", "").split("/")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValidationError("AA/YY biçiminde yazın (ör. 08/28).")
        month, year = int(parts[0]), int(parts[1]) % 100 + 2000
        if not 1 <= month <= 12:
            raise ValidationError("Ay 01-12 arasında olmalı.")
        today = date.today()
        if (year, month) < (today.year, today.month):
            raise ValidationError("Kartın süresi dolmuş.")

    def validate_cvc(self, field):
        if not _digits(field.data) == (field.data or "").strip() or len(_digits(field.data)) not in (3, 4):
            raise ValidationError("CVC 3 veya 4 haneli olmalı.")

    def to_card(self):
        from app.integrations.payment_api import CardInfo
        month, year = self.expiry.data.replace(" ", "").split("/")
        return CardInfo(holder=self.card_holder.data.strip(), number=_digits(self.card_number.data),
                        exp_month=int(month), exp_year=int(year) % 100 + 2000, cvc=self.cvc.data.strip())
