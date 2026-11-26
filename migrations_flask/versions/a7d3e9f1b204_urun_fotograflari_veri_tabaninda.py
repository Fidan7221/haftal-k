"""urun fotograflari veri tabaninda (product_images)

v0.10.4: Render'ın ücretsiz planında disk geçici olduğu için (her güncellemede ve uyandırmada
yüklenen dosyalar silinir) ürün fotoğrafları veri tabanında saklanır. Ürün bu tabloya
products.image_path = "db/<id>" ile bağlanır.

Revision ID: a7d3e9f1b204
Revises: c612d580ebbd
Create Date: 2026-11-26 23:40:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7d3e9f1b204'
down_revision = 'c612d580ebbd'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('product_images',
    sa.Column('content_type', sa.String(length=30), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('product_images')
