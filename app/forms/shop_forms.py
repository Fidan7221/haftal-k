"""İlan, sepet, ödeme ve sipariş formları (Hafta 7).

Formdaki doğrulama kullanıcıya hızlı geri bildirim içindir. Asıl iş kuralları
servis katmanında TEKRAR kontrol edilir; çünkü form atlanabilir (ör. biri doğrudan
POST isteği gönderebilir).
"""
from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional


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
