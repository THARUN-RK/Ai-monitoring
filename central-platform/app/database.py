import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cicada.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def init_db_schema():
    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                # 1. Check metric_records columns
                existing_metric_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(metric_records)").fetchall()}
                if existing_metric_cols:
                    metric_additions = [
                        ("source_timestamp", "DATETIME"),
                        ("collector_timestamp", "DATETIME"),
                        ("ingestion_timestamp", "DATETIME"),
                        ("processing_timestamp", "DATETIME"),
                        ("sequence_number", "INTEGER DEFAULT 0"),
                        ("ingestion_delay_ms", "FLOAT DEFAULT 0.0"),
                        ("processing_delay_ms", "FLOAT DEFAULT 0.0"),
                        ("total_e2e_delay_ms", "FLOAT DEFAULT 0.0"),
                        ("is_delayed", "BOOLEAN DEFAULT 0"),
                        ("is_out_of_order", "BOOLEAN DEFAULT 0"),
                    ]
                    for col_name, col_type in metric_additions:
                        if col_name not in existing_metric_cols:
                            try:
                                conn.exec_driver_sql(f"ALTER TABLE metric_records ADD COLUMN {col_name} {col_type}")
                            except Exception:
                                pass

                # 2. Check collector_records columns
                existing_col_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(collector_records)").fetchall()}
                if existing_col_cols:
                    collector_additions = [
                        ("last_sequence_number", "INTEGER DEFAULT 0"),
                        ("total_events_received", "INTEGER DEFAULT 0"),
                        ("duplicate_events_count", "INTEGER DEFAULT 0"),
                        ("delayed_events_count", "INTEGER DEFAULT 0"),
                        ("out_of_order_count", "INTEGER DEFAULT 0"),
                    ]
                    for col_name, col_type in collector_additions:
                        if col_name not in existing_col_cols:
                            try:
                                conn.exec_driver_sql(f"ALTER TABLE collector_records ADD COLUMN {col_name} {col_type}")
                            except Exception:
                                pass

                # 3. Check egress_audit_records columns
                existing_egress_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(egress_audit_records)").fetchall()}
                if existing_egress_cols:
                    egress_additions = [
                        ("policy_version", "VARCHAR(64) DEFAULT 'v1.0-allowlist'"),
                        ("policy_decision", "VARCHAR(32) DEFAULT 'APPROVED'"),
                        ("payload_hash", "VARCHAR(64) DEFAULT ''"),
                        ("payload_size_bytes", "INTEGER DEFAULT 0"),
                        ("fields_permitted", "TEXT DEFAULT '[]'"),
                        ("fields_redacted", "TEXT DEFAULT '[]'"),
                        ("raw_sample_redacted", "TEXT DEFAULT '{}'"),
                        ("exact_outbound_payload", "TEXT DEFAULT '{}'"),
                    ]
                    for col_name, col_type in egress_additions:
                        if col_name not in existing_egress_cols:
                            try:
                                conn.exec_driver_sql(f"ALTER TABLE egress_audit_records ADD COLUMN {col_name} {col_type}")
                            except Exception:
                                pass
                conn.commit()
        except Exception as err:
            print(f"[DB MIGRATION NOTICE] {err}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
