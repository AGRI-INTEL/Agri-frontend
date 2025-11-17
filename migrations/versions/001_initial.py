"""Initial migration

Revision ID: 001_initial
Revises: 
Create Date: 2025-09-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "postgis";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # Create enum types
    # op.execute("CREATE TYPE user_role AS ENUM ('admin', 'analyst', 'user', 'guest');")
    op.execute("CREATE TYPE unit_type AS ENUM ('tonnes', 'hectares', 'kg/ha', 'mm', 'celsius', 'percent', 'usd');")
    op.execute("CREATE TYPE indicator_type AS ENUM ('gdp', 'inflation', 'agricultural_gdp', 'employment', 'export', 'import', 'investment');")

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('role', sa.Enum('admin', 'analyst', 'user', 'guest', name='user_role'), nullable=False),
        sa.Column('phone_number', sa.String(50)),
        sa.Column('organization', sa.String(255)),
        sa.Column('country', sa.String(100)),
        sa.Column('bio', sa.Text),
        sa.Column('avatar_url', sa.String(500)),
        sa.Column('language', sa.String(10), nullable=False, server_default='fr'),
        sa.Column('timezone', sa.String(50), nullable=False, server_default='UTC'),
        sa.Column('theme', sa.String(20), nullable=False, server_default='light'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_login', sa.DateTime(timezone=True)),
        sa.Column('failed_login_attempts', sa.Integer, nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True)),
        sa.Column('password_changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username')
    )
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_username', 'users', ['username'])

    # Create staging_production table
    op.create_table(
        'staging_production',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('country_code', sa.String(3), nullable=False),
        sa.Column('country_name', sa.String(100), nullable=False),
        sa.Column('crop_code', sa.Integer(), nullable=False),
        sa.Column('crop_name', sa.String(100), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('unit', sa.Enum('tonnes', 'hectares', 'kg/ha', name='unit_type'), nullable=False),
        sa.Column('source', sa.String(100)),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('quality_score', sa.Float(), server_default='1.0'),
        sa.Column('is_validated', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True)),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('country_code', 'crop_code', 'year', name='uix_production_country_crop_year')
    )
    op.create_index('ix_production_search', 'staging_production', ['country_code', 'crop_name', 'year'])

    # Create staging_weather table with PostGIS support
    op.create_table(
        'staging_weather',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('city', sa.String(100), nullable=False),
        sa.Column('country', sa.String(100), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=False),
        sa.Column('humidity', sa.Float(), nullable=False),
        sa.Column('precipitation', sa.Float(), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lon', sa.Float(), nullable=False),
        sa.Column('elevation', sa.Float()),
        sa.Column('weather_condition', sa.String(50)),
        sa.Column('wind_speed', sa.Float()),
        sa.Column('wind_direction', sa.Float()),
        sa.Column('pressure', sa.Float()),
        sa.Column('source', sa.String(100)),
        sa.Column('quality_score', sa.Float(), server_default='1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True)),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_weather_location_date', 'staging_weather', ['city', 'country', 'date'])
    op.execute('CREATE INDEX ix_weather_coords ON staging_weather USING gist (ll_to_earth(lat, lon));')

def downgrade():
    op.drop_index('ix_weather_coords', table_name='staging_weather')
    op.drop_index('ix_weather_location_date', table_name='staging_weather')
    op.drop_table('staging_weather')
    
    op.drop_index('ix_production_search', table_name='staging_production')
    op.drop_table('staging_production')
    
    op.drop_index('ix_users_username', table_name='users')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
    
    op.execute('DROP TYPE indicator_type;')
    op.execute('DROP TYPE unit_type;')
    op.execute('DROP TYPE user_role;')
    
    op.execute('DROP EXTENSION IF EXISTS "postgis";')
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm";')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp";')