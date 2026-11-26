"""tahmin gerekceleri (price_predictions.reasons)

v0.10.7: Yapay zekânın gerekçeleri kaydedilir; kayıtlı öneri yeniden gösterilirken kaybolmaz.

Revision ID: b81c4e2d9a57
Revises: a7d3e9f1b204
Create Date: 2026-11-27 00:45:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b81c4e2d9a57'
down_revision = 'a7d3e9f1b204'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('price_predictions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reasons', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('price_predictions', schema=None) as batch_op:
        batch_op.drop_column('reasons')
