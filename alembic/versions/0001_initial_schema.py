"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-30

NOTA PARA DBs DE PRODUÇÃO EXISTENTES:
  O banco foi criado anteriormente via create_tables() imperativo.
  Para não tentar recriar tabelas já existentes, marque o banco existente
  com o revision atual ANTES de rodar upgrade:

      alembic stamp 0001_initial_schema

  A partir daí, futuras migrations serão aplicadas normalmente.
  Em instâncias novas (Docker Compose, CI, staging), apenas:

      alembic upgrade head

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Enum types  (idempotent via DO/EXCEPTION)
    # ------------------------------------------------------------------
    conn.execute(_sql("""
        DO $$ BEGIN
            CREATE TYPE providertype AS ENUM (
                'AWS', 'GCP', 'AZURE', 'OCI', 'CLOUDSTACK'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))

    conn.execute(_sql("""
        DO $$ BEGIN
            CREATE TYPE resourcetype AS ENUM (
                'VM', 'STORAGE', 'STORAGE_FLASH', 'STORAGE_SAS',
                'NETWORK', 'DATABASE', 'LOADBALANCER', 'KUBERNETES', 'FILESTORE'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))

    # Extend existing resourcetype enum with values added after initial deploy.
    for val in ("KUBERNETES", "FILESTORE", "STORAGE_FLASH", "STORAGE_SAS"):
        conn.execute(_sql(f"ALTER TYPE resourcetype ADD VALUE IF NOT EXISTS '{val}'"))

    conn.execute(_sql("""
        DO $$ BEGIN
            CREATE TYPE resourcestatus AS ENUM (
                'ACTIVE', 'STOPPED', 'MIGRATING', 'MIGRATED'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))

    conn.execute(_sql("""
        DO $$ BEGIN
            CREATE TYPE migrationstatus AS ENUM (
                'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))

    # ------------------------------------------------------------------
    # 2. Tables  (all use IF NOT EXISTS — safe on existing production DBs)
    # ------------------------------------------------------------------

    # clients
    conn.execute(_sql("""
        CREATE TABLE IF NOT EXISTS clients (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(255) NOT NULL,
            description TEXT,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_clients_id   ON clients (id)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_clients_name ON clients (name)"))

    # cloud_providers
    conn.execute(_sql("""
        CREATE TABLE IF NOT EXISTS cloud_providers (
            id               SERIAL PRIMARY KEY,
            client_id        INTEGER REFERENCES clients(id) ON DELETE CASCADE,
            name             VARCHAR(255)  NOT NULL,
            type             providertype  NOT NULL,
            credentials_json TEXT,
            is_active        BOOLEAN       NOT NULL DEFAULT TRUE,
            created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_cloud_providers_id        ON cloud_providers (id)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_cloud_providers_name      ON cloud_providers (name)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_cloud_providers_type      ON cloud_providers (type)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_cloud_providers_client_id ON cloud_providers (client_id)"))

    # client_id FK – add if the column was never added by the old imperative DDL
    conn.execute(_sql("""
        DO $$ BEGIN
            ALTER TABLE cloud_providers
                ADD COLUMN client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$;
    """))

    # cloud_resources
    conn.execute(_sql("""
        CREATE TABLE IF NOT EXISTS cloud_resources (
            id            SERIAL PRIMARY KEY,
            provider_id   INTEGER       NOT NULL REFERENCES cloud_providers(id) ON DELETE CASCADE,
            resource_type resourcetype  NOT NULL,
            name          VARCHAR(255)  NOT NULL,
            region        VARCHAR(128),
            external_id   VARCHAR(512),
            specs_json    TEXT,
            status        resourcestatus NOT NULL DEFAULT 'ACTIVE',
            created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_cloud_resources_id            ON cloud_resources (id)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_cloud_resources_provider_id   ON cloud_resources (provider_id)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_cloud_resources_resource_type ON cloud_resources (resource_type)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_cloud_resources_name          ON cloud_resources (name)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_cloud_resources_external_id   ON cloud_resources (external_id)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_cloud_resources_status        ON cloud_resources (status)"))

    # migration_jobs
    conn.execute(_sql("""
        CREATE TABLE IF NOT EXISTS migration_jobs (
            id                 SERIAL PRIMARY KEY,
            name               VARCHAR(255)    NOT NULL,
            source_provider_id INTEGER         NOT NULL REFERENCES cloud_providers(id) ON DELETE RESTRICT,
            target_provider_id INTEGER         NOT NULL REFERENCES cloud_providers(id) ON DELETE RESTRICT,
            status             migrationstatus NOT NULL DEFAULT 'PENDING',
            resources_json     TEXT,
            progress_percent   FLOAT           NOT NULL DEFAULT 0.0,
            error_message      TEXT,
            started_at         TIMESTAMPTZ,
            completed_at       TIMESTAMPTZ,
            created_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_migration_jobs_id                 ON migration_jobs (id)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_migration_jobs_name               ON migration_jobs (name)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_migration_jobs_source_provider_id ON migration_jobs (source_provider_id)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_migration_jobs_target_provider_id ON migration_jobs (target_provider_id)"))
    conn.execute(_sql("CREATE INDEX IF NOT EXISTS ix_migration_jobs_status             ON migration_jobs (status)"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(_sql("DROP TABLE IF EXISTS migration_jobs   CASCADE"))
    conn.execute(_sql("DROP TABLE IF EXISTS cloud_resources  CASCADE"))
    conn.execute(_sql("DROP TABLE IF EXISTS cloud_providers  CASCADE"))
    conn.execute(_sql("DROP TABLE IF EXISTS clients          CASCADE"))
    conn.execute(_sql("DROP TYPE  IF EXISTS migrationstatus"))
    conn.execute(_sql("DROP TYPE  IF EXISTS resourcestatus"))
    conn.execute(_sql("DROP TYPE  IF EXISTS resourcetype"))
    conn.execute(_sql("DROP TYPE  IF EXISTS providertype"))


# ---------------------------------------------------------------------------
# Helper — wrap raw SQL strings for SQLAlchemy execute()
# ---------------------------------------------------------------------------
from sqlalchemy import text as _text  # noqa: E402


def _sql(stmt: str):
    return _text(stmt)
