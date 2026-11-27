"""bildirimler (notifications) — Hafta 12

Revision ID: c4e7a19d3b60
Revises: b81c4e2d9a57
Create Date: 2026-11-27 21:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4e7a19d3b60'
down_revision = 'b81c4e2d9a57'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('notifications',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('message', sa.String(length=255), nullable=False),
    sa.Column('link', sa.String(length=255), nullable=True),
    sa.Column('is_read', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notifications_is_read'), ['is_read'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notifications_user_id'))
        batch_op.drop_index(batch_op.f('ix_notifications_is_read'))
    op.drop_table('notifications')
