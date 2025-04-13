from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("doctor_profile")]

    columns_to_add = {
        "address": sa.Column("address", sa.String(length=255), nullable=True),
        "city": sa.Column("city", sa.String(length=100), nullable=True),
        "state": sa.Column("state", sa.String(length=100), nullable=True),
        "postal_code": sa.Column("postal_code", sa.String(length=50), nullable=True),
        "country": sa.Column("country", sa.String(length=100), nullable=True),
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            op.add_column("doctor_profile", col_def)

def downgrade():
    pass