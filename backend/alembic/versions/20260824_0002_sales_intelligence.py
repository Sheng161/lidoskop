"""sales intelligence entities

Revision ID: 20260824_0002
Revises: 20260824_0001
"""

from alembic import op
from app.models import Base

revision = "20260824_0002"
down_revision = "20260824_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # checkfirst поддерживает как чистую установку, так и обновление раннего MVP.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # История сделок намеренно не удаляется автоматически при откате слоя.
    pass
