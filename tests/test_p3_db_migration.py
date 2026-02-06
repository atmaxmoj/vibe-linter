"""Database Migration workflow tests."""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# ─── Helpers ───

def _walk_to_migration_review(h):
    """Start -> submit 1.1 -> arrive at 1.2 Migration review (waiting)."""
    h.start()
    h.submit({})
    assert h.step == "1.2 Migration review"
    assert h.status == "waiting"


def _walk_to_verify(h):
    """Start -> through review -> backup -> execute -> arrive at 2.3 Verify."""
    _walk_to_migration_review(h)
    h.approve()
    h.submit_goto("2.1 Backup database")
    h.submit({})   # 2.1 -> 2.2
    h.submit({})   # 2.2 -> 2.3
    assert h.step == "2.3 Verify migration"
    assert h.status == "running"


# ═══════════════════════════════════════════════════════
# Existing scenarios (unchanged)
# ═══════════════════════════════════════════════════════

def test_migration_succeeds_first_try(harness_factory):
    """Scenario 1: Add tenant_id column to 50M-row orders table using online DDL -- succeeds first try."""
    h = harness_factory("p3-db-migration.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Plan migration strategy"
    assert h.status == "running"

    # 1.1 Plan the migration strategy
    r = h.submit({
        "database": "PostgreSQL 16",
        "table": "orders",
        "rows": "50M",
        "change": "ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'",
        "strategy": "Online DDL with pg_repack to avoid long locks",
        "estimated_duration": "~15 minutes with concurrent reads",
        "rollback_plan": "ALTER TABLE orders DROP COLUMN tenant_id",
        "maintenance_window": "Saturday 2am-4am UTC",
    })
    assert r
    assert r.new_step == "1.2 Migration review"
    assert h.step == "1.2 Migration review"
    assert h.status == "waiting"

    # 1.2 DBA approves the migration plan
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.1 Backup database")
    assert r
    assert r.new_step == "2.1 Backup database"
    assert h.step == "2.1 Backup database"

    # 2.1 Take a backup
    r = h.submit({
        "method": "pg_basebackup with WAL archiving",
        "backup_id": "bkp_orders_20260205_0200",
        "size": "48GB",
        "duration": "12 minutes",
        "verified": "pg_verifybackup passed",
    })
    assert r
    assert r.new_step == "2.2 Execute migration"
    assert h.step == "2.2 Execute migration"

    # 2.2 Execute the migration
    r = h.submit({
        "command": "ALTER TABLE orders ADD COLUMN tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'",
        "duration": "14 minutes",
        "locks_held": "AccessExclusiveLock for 200ms (fast default value)",
        "replication_lag": "peak 3s, recovered to 0 within 1 minute",
    })
    assert r
    assert r.new_step == "2.3 Verify migration"
    assert h.step == "2.3 Verify migration"

    # 2.3 Verify -- all checks pass
    r = h.submit_goto("3.1 Post-migration validation")
    assert r
    assert r.new_step == "3.1 Post-migration validation"
    assert h.step == "3.1 Post-migration validation"

    # 3.1 Post-migration validation
    r = h.submit({
        "checks": [
            "SELECT count(*) FROM orders WHERE tenant_id IS NULL -- 0 rows",
            "Application health check -- 200 OK",
            "Query latency p99 -- 45ms (baseline: 42ms, acceptable)",
            "Replication lag -- 0s",
        ],
        "result": "All validation checks passed",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_partial_failure_fix_reverify(harness_factory):
    """Scenario 2: Split monolithic users table -- foreign key constraints fail on 2 of 8 tables, fix and re-verify."""
    h = harness_factory("p3-db-migration.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "database": "PostgreSQL 15",
        "change": "Split monolithic users table into users + user_profiles + user_preferences (8 FK references)",
        "strategy": "Multi-step: create new tables, backfill, swap FKs, drop old columns",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Backup database")
    assert r
    r = h.submit({"backup_id": "bkp_users_split_20260205", "method": "pg_dump with --jobs=4"})
    assert r
    r = h.submit({
        "steps_executed": [
            "CREATE TABLE user_profiles (user_id UUID REFERENCES users(id), ...)",
            "INSERT INTO user_profiles SELECT ... FROM users",
            "ALTER TABLE orders ADD CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id)",
        ],
        "result": "6 of 8 FK constraints created successfully, 2 failed",
    })
    assert r
    assert r.new_step == "2.3 Verify migration"
    assert h.step == "2.3 Verify migration"

    # Partial failure 1: sessions table has orphaned user_ids
    r = h.submit_goto("2.4 Fix partial failure")
    assert r
    assert r.new_step == "2.4 Fix partial failure"
    assert h.step == "2.4 Fix partial failure"

    r = h.submit({
        "table": "sessions",
        "issue": "47 rows reference deleted users -- orphaned sessions from before soft-delete was added",
        "fix": "DELETE FROM sessions WHERE user_id NOT IN (SELECT id FROM users) -- 47 rows removed",
    })
    assert r
    assert r.new_step == "2.3 Verify migration"
    assert h.step == "2.3 Verify migration"

    # Partial failure 2: audit_logs has user_ids that were hard-deleted
    r = h.submit_goto("2.4 Fix partial failure")
    assert r
    assert r.new_step == "2.4 Fix partial failure"
    assert h.step == "2.4 Fix partial failure"

    r = h.submit({
        "table": "audit_logs",
        "issue": "1,203 rows reference hard-deleted users from 2024 data cleanup",
        "fix": "SET audit_logs.user_id = NULL WHERE user_id NOT IN (SELECT id FROM users), made FK DEFERRABLE",
    })
    assert r
    assert r.new_step == "2.3 Verify migration"
    assert h.step == "2.3 Verify migration"

    # All 8 FK constraints now valid
    r = h.submit_goto("3.1 Post-migration validation")
    assert r
    assert r.new_step == "3.1 Post-migration validation"
    assert h.step == "3.1 Post-migration validation"

    r = h.submit({
        "checks": ["All 8 FK constraints valid", "user_profiles row count matches users", "Application smoke tests pass"],
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_full_failure_rollback_replan(harness_factory):
    """Scenario 3: UUID migration on payments table causes replication failure -- full rollback, replan with blue-green."""
    h = harness_factory("p3-db-migration.yaml")
    r = h.start()
    assert r

    # First plan: in-place ALTER COLUMN from BIGINT to UUID
    r = h.submit({
        "database": "PostgreSQL 15 with 2 read replicas",
        "table": "payments (120M rows)",
        "change": "ALTER COLUMN id TYPE UUID USING gen_random_uuid()",
        "strategy": "In-place column type change with table rewrite",
        "risk": "Table rewrite on 120M rows will hold ACCESS EXCLUSIVE lock",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Backup database")
    assert r
    r = h.submit({"backup_id": "bkp_payments_uuid_attempt1", "size": "95GB"})
    assert r
    r = h.submit({
        "command": "ALTER TABLE payments ALTER COLUMN id TYPE UUID USING gen_random_uuid()",
        "result": "Lock held for 45 minutes, replicas fell behind by 20GB WAL, primary OOM killed",
    })
    assert r
    assert r.new_step == "2.3 Verify migration"
    assert h.step == "2.3 Verify migration"

    # Full rollback: restore from backup
    r = h.submit_goto("2.5 Full rollback")
    assert r
    assert r.new_step == "2.5 Full rollback"
    assert h.step == "2.5 Full rollback"

    r = h.submit({
        "action": "pg_restore from bkp_payments_uuid_attempt1",
        "duration": "28 minutes",
        "data_loss": "None -- restored to pre-migration state",
        "lesson": "Cannot ALTER TYPE on 120M row table in-place -- need blue-green approach",
    })
    assert r
    assert r.new_step == "1.1 Plan migration strategy"
    assert h.step == "1.1 Plan migration strategy"
    assert h.status == "running"

    # Replan: blue-green with shadow table
    r = h.submit({
        "database": "PostgreSQL 15",
        "table": "payments (120M rows)",
        "change": "Migrate BIGINT id to UUID using shadow table approach",
        "strategy": "Blue-green: create payments_v2 with UUID, dual-write, backfill, swap",
        "steps": [
            "CREATE TABLE payments_v2 (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), ...)",
            "Deploy dual-write: INSERT into both tables",
            "Backfill payments_v2 from payments in batches of 10k",
            "Swap: RENAME TABLE payments TO payments_old, payments_v2 TO payments",
        ],
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Backup database")
    assert r
    r = h.submit({"backup_id": "bkp_payments_uuid_attempt2"})
    assert r
    r = h.submit({
        "result": "Blue-green migration completed in 2 hours with zero downtime",
        "backfill_batches": 12000,
        "max_replication_lag": "2s",
    })
    assert r
    r = h.submit_goto("3.1 Post-migration validation")
    assert r
    r = h.submit({
        "checks": ["Row count matches: 120,847,293", "All FKs valid", "p99 latency: 38ms (baseline: 35ms)"],
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_multiple_failures_stop(harness_factory):
    """Scenario 4: Sharding migration keeps hitting edge cases -- 5 partial failures, DBA stops to escalate."""
    h = harness_factory("p3-db-migration.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "database": "PostgreSQL 15",
        "table": "events (800M rows)",
        "change": "Partition by tenant_id using hash partitioning (16 partitions)",
        "strategy": "pg_partman with incremental migration",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Backup database")
    assert r
    r = h.submit({"backup_id": "bkp_events_sharding", "size": "320GB"})
    assert r
    r = h.submit({
        "command": "SELECT partman.create_parent('public.events', 'tenant_id', 'hash', '16')",
        "result": "Partitions created, data migration started",
    })
    assert r

    # 5 consecutive partial failures -- each batch reveals new edge cases
    fixes = [
        {"issue": "Batch 3: NULL tenant_id in 12k legacy rows", "fix": "SET tenant_id = 'legacy' WHERE tenant_id IS NULL"},
        {"issue": "Batch 7: duplicate PKs across partitions", "fix": "Added partition key to composite PK"},
        {"issue": "Batch 12: trigger on events table references old schema", "fix": "Updated trigger to use NEW.tenant_id"},
        {"issue": "Batch 15: cross-partition FK from event_metadata", "fix": "Converted FK to application-level check"},
        {"issue": "Batch 16: TOAST table corruption on partition 9", "fix": "REINDEX on partition_9, pg_repack"},
    ]
    for fix_data in fixes:
        assert h.step == "2.3 Verify migration"
        r = h.submit_goto("2.4 Fix partial failure")
        assert r
        assert r.new_step == "2.4 Fix partial failure"
        r = h.submit(fix_data)
        assert r
        assert r.new_step == "2.3 Verify migration"

    assert h.step == "2.3 Verify migration"

    # DBA stops to escalate to PostgreSQL support team
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.3 Verify migration"


def test_review_rejected(harness_factory):
    """Scenario 5: DBA rejects plan to run ALTER TABLE during peak hours -- must use maintenance window."""
    h = harness_factory("p3-db-migration.yaml")
    r = h.start()
    assert r

    # Plan rejected: running during peak hours
    r = h.submit({
        "database": "PostgreSQL 16",
        "table": "transactions (200M rows)",
        "change": "CREATE INDEX CONCURRENTLY idx_transactions_merchant ON transactions(merchant_id)",
        "strategy": "Run CREATE INDEX CONCURRENTLY during business hours",
        "issue": "DBA rejects: CONCURRENTLY still doubles I/O, will impact p99 during peak",
    })
    assert r
    assert r.new_step == "1.2 Migration review"
    assert h.step == "1.2 Migration review"
    assert h.status == "waiting"

    # DBA rejects: must use maintenance window
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("1.1 Plan migration strategy")
    assert r
    assert r.new_step == "1.1 Plan migration strategy"
    assert h.step == "1.1 Plan migration strategy"
    assert h.status == "running"

    # Revised plan: maintenance window + reduced fillfactor
    r = h.submit({
        "database": "PostgreSQL 16",
        "table": "transactions (200M rows)",
        "change": "CREATE INDEX CONCURRENTLY idx_transactions_merchant ON transactions(merchant_id) WITH (fillfactor=90)",
        "strategy": "Run during Saturday 3am-5am maintenance window, CONCURRENTLY with reduced fillfactor",
        "monitoring": "Watch pg_stat_progress_create_index for completion estimate",
    })
    assert r
    assert r.new_step == "1.2 Migration review"
    assert h.step == "1.2 Migration review"

    # DBA approves revised plan
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.1 Backup database")
    assert r
    assert r.new_step == "2.1 Backup database"
    assert h.step == "2.1 Backup database"


def test_stop_discuss_resume(harness_factory):
    """Scenario 6: Stop before executing DROP COLUMN on production -- need VP approval for irreversible change."""
    h = harness_factory("p3-db-migration.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "database": "PostgreSQL 15",
        "table": "users",
        "change": "DROP COLUMN legacy_password_md5 (deprecated since 2024, all users migrated to bcrypt)",
        "strategy": "Direct DROP COLUMN -- irreversible, requires VP Engineering sign-off",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Backup database")
    assert r
    r = h.submit({"backup_id": "bkp_users_drop_md5", "method": "pg_dump --table=users"})
    assert r
    assert r.new_step == "2.2 Execute migration"
    assert h.step == "2.2 Execute migration"

    # Stop: need VP approval before irreversible DROP COLUMN
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Execute migration"

    # VP approved, resume
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Execute migration"

    r = h.submit({
        "command": "ALTER TABLE users DROP COLUMN legacy_password_md5",
        "duration": "instant (PostgreSQL only marks column as dropped)",
        "space_reclaimed": "0 bytes (need VACUUM FULL for actual reclaim)",
    })
    assert r
    r = h.submit_goto("3.1 Post-migration validation")
    assert r
    r = h.submit({
        "checks": ["Application login works with bcrypt", "No queries reference legacy_password_md5", "ORM model updated"],
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_skip_backup(harness_factory):
    """Scenario 7: Skip backup -- running migration on ephemeral staging environment seeded from fixtures."""
    h = harness_factory("p3-db-migration.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "database": "PostgreSQL 16 (staging)",
        "environment": "staging -- ephemeral Docker container, data seeded from fixtures",
        "table": "products",
        "change": "ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', name || ' ' || description)) STORED",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Backup database")
    assert r
    assert r.new_step == "2.1 Backup database"
    assert h.step == "2.1 Backup database"

    # Skip backup on staging -- data is ephemeral
    r = h.skip("Staging environment with fixture data -- no backup needed, can recreate in 30 seconds")
    assert r
    assert r.new_step == "2.2 Execute migration"
    assert h.step == "2.2 Execute migration"

    r = h.submit({
        "command": "ALTER TABLE products ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', name || ' ' || description)) STORED",
        "duration": "3 seconds (staging has only 10k rows)",
    })
    assert r
    r = h.submit_goto("3.1 Post-migration validation")
    assert r
    r = h.submit({
        "checks": ["Full-text search query returns correct results", "GIN index on search_vector created", "Insert trigger works"],
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_complete_then_reset(harness_factory):
    """Scenario 8: Complete index migration, reset to plan the next migration (adding enum column)."""
    h = harness_factory("p3-db-migration.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "database": "PostgreSQL 16",
        "table": "orders",
        "change": "CREATE INDEX CONCURRENTLY idx_orders_status_created ON orders(status, created_at DESC)",
        "strategy": "CONCURRENTLY during low-traffic window",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Backup database")
    assert r
    r = h.submit({"backup_id": "bkp_orders_index"})
    assert r
    r = h.submit({
        "command": "CREATE INDEX CONCURRENTLY idx_orders_status_created ON orders(status, created_at DESC)",
        "duration": "8 minutes on 50M rows",
    })
    assert r
    r = h.submit_goto("3.1 Post-migration validation")
    assert r
    r = h.submit({"checks": ["Index used by query planner (EXPLAIN shows Index Scan)", "Query time dropped from 2.3s to 45ms"]})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    r = h.submit({})
    assert not r

    # Reset for next migration: adding payment_method enum column
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Plan migration strategy"
    assert h.status == "running"


def test_goto_verification(harness_factory):
    """Scenario 9: Migration already executed by ops team -- jump to post-migration validation to verify."""
    h = harness_factory("p3-db-migration.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "database": "PostgreSQL 15",
        "table": "sessions",
        "change": "ALTER TABLE sessions ADD COLUMN ip_address INET",
        "note": "Migration was executed by ops team during incident response -- need to validate",
    })
    assert r
    assert h.step == "1.2 Migration review"
    assert h.status == "waiting"

    # Cannot submit while waiting
    r = h.submit_goto("2.1 Backup database")
    assert not r
    assert "waiting" in r.message

    # Jump directly to validation -- migration already done
    r = h.goto("3.1 Post-migration validation")
    assert r
    assert r.new_step == "3.1 Post-migration validation"
    assert h.step == "3.1 Post-migration validation"
    assert h.status == "running"

    r = h.submit({
        "checks": [
            "Column ip_address exists: YES",
            "Column type is INET: YES",
            "NULL values allowed: YES (correct, existing rows have no IP)",
            "Application writes IP on new sessions: verified",
        ],
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_modify_yaml_add_snapshot(harness_factory):
    """Scenario 10: Hot-reload YAML to add RDS snapshot step after learning pg_dump is too slow for 500GB database."""
    h = harness_factory("p3-db-migration.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "database": "AWS RDS PostgreSQL 16 (500GB, db.r6g.4xlarge)",
        "table": "analytics_events",
        "change": "Partition by date range (monthly partitions)",
        "note": "pg_dump backup will take 4+ hours -- need RDS snapshot instead",
    })
    assert r
    assert h.step == "1.2 Migration review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.1 Backup database")
    assert r
    assert r.new_step == "2.1 Backup database"
    assert h.step == "2.1 Backup database"

    # Add RDS snapshot step via hot-reload
    yaml_content = """名称: Database Migration
描述: No loop, 3-way (success/partial-failure/full-rollback), cross-phase fallback

步骤:
  - 1.1 Plan migration strategy

  - 1.2 Migration review:
      类型: wait
      下一步:
        - 如果: "migration plan approved"
          去: 2.1 Backup database
        - 去: 1.1 Plan migration strategy

  - 2.1 Backup database

  - 2.1.5 Create snapshot:
      下一步: 2.2 Execute migration

  - 2.2 Execute migration

  - 2.3 Verify migration:
      下一步:
        - 如果: "migration fully successful"
          去: 3.1 Post-migration validation
        - 如果: "partial failure, some tables need fixing"
          去: 2.4 Fix partial failure
        - 去: 2.5 Full rollback

  - 2.4 Fix partial failure:
      下一步: 2.3 Verify migration

  - 2.5 Full rollback:
      下一步: 1.1 Plan migration strategy

  - 3.1 Post-migration validation

  - Done:
      类型: terminate
      原因: Database migration complete
"""
    h.reload_yaml(yaml_content)

    r = h.goto("2.1.5 Create snapshot")
    assert r
    assert r.new_step == "2.1.5 Create snapshot"
    assert h.step == "2.1.5 Create snapshot"
    assert h.status == "running"

    r = h.submit({
        "command": "aws rds create-db-snapshot --db-instance-identifier prod-analytics --db-snapshot-identifier pre-partition-20260205",
        "duration": "12 minutes (incremental snapshot from last automated backup)",
        "snapshot_id": "pre-partition-20260205",
    })
    assert r
    assert r.new_step == "2.2 Execute migration"
    assert h.step == "2.2 Execute migration"


# ═══════════════════════════════════════════════════════
# Dimension tests: Data accumulation
# ═══════════════════════════════════════════════════════

def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()

    h.submit({"plan": "blue-green deploy"})
    data = h.state.data
    assert "1.1 Plan migration strategy" in data
    assert data["1.1 Plan migration strategy"]["plan"] == "blue-green deploy"

    h.approve()
    h.submit_goto("2.1 Backup database")
    h.submit({"backup": "snapshot_001"})
    data = h.state.data
    assert "2.1 Backup database" in data
    assert data["2.1 Backup database"]["backup"] == "snapshot_001"


def test_s2_data_after_partial_fix(harness_factory):
    """Data persists through partial failure fix cycle."""
    h = harness_factory("p3-db-migration.yaml")
    _walk_to_verify(h)

    h.submit_goto("2.4 Fix partial failure")
    h.submit({"fix": "alter table users"})
    data = h.state.data
    assert "2.4 Fix partial failure" in data
    assert data["2.4 Fix partial failure"]["fix"] == "alter table users"

    # Back at verify, fix data still present
    assert h.step == "2.3 Verify migration"
    data = h.state.data
    assert "2.4 Fix partial failure" in data


# ═══════════════════════════════════════════════════════
# Dimension tests: History audit trail
# ═══════════════════════════════════════════════════════

def test_s1_history_audit_trail(harness_factory):
    """After walkthrough, history contains expected action sequence."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.submit({})
    h.approve()
    h.submit_goto("2.1 Backup database")
    h.submit({})
    h.submit({})
    h.submit_goto("3.1 Post-migration validation")
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "approve" in actions
    assert "submit" in actions
    assert "terminate" in actions[-1]


def test_s3_history_after_rollback(harness_factory):
    """History records rollback path correctly."""
    h = harness_factory("p3-db-migration.yaml")
    _walk_to_verify(h)

    h.submit_goto("2.5 Full rollback")
    h.submit({})
    assert h.step == "1.1 Plan migration strategy"

    history = h.get_history(30)
    actions = [e["action"] for e in history]
    assert "submit" in actions
    assert "transition" in actions


# ═══════════════════════════════════════════════════════
# Dimension tests: Cross-executor recovery
# ═══════════════════════════════════════════════════════

def test_cross_executor_at_migration_review(harness_factory):
    """Close at migration review, reopen, state persists."""
    h = harness_factory("p3-db-migration.yaml")
    _walk_to_migration_review(h)

    h.new_executor()

    assert h.step == "1.2 Migration review"
    assert h.status == "waiting"

    h.approve()
    r = h.submit_goto("2.1 Backup database")
    assert r
    assert h.step == "2.1 Backup database"


def test_cross_executor_at_verify(harness_factory):
    """Close at verify step, reopen, state persists."""
    h = harness_factory("p3-db-migration.yaml")
    _walk_to_verify(h)

    h.new_executor()

    assert h.step == "2.3 Verify migration"
    assert h.status == "running"


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.goto("3.1 Post-migration validation")
    h.submit({})
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


# ═══════════════════════════════════════════════════════
# Dimension tests: Node validation
# ═══════════════════════════════════════════════════════

def test_node_validates_plan(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()

    h.register_node(
        "1.1 Plan migration strategy",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("strategy") else "must include strategy",
        ),
    )

    r = h.submit({"notes": "no strategy"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"strategy": "blue-green"})
    assert r
    assert r.new_step == "1.2 Migration review"


def test_node_validates_backup(harness_factory):
    """Validate node on backup step."""
    h = harness_factory("p3-db-migration.yaml")
    _walk_to_migration_review(h)
    h.approve()
    h.submit_goto("2.1 Backup database")

    h.register_node(
        "2.1 Backup database",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("backup_id") else "must include backup_id",
        ),
    )

    r = h.submit({"comment": "no id"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"backup_id": "bkp_001"})
    assert r


# ═══════════════════════════════════════════════════════
# Dimension tests: Node archival
# ═══════════════════════════════════════════════════════

def test_node_archives_fixes(harness_factory):
    """Archive node writes each partial fix to SQLite."""
    h = harness_factory("p3-db-migration.yaml")
    _walk_to_verify(h)

    h.register_node(
        "2.4 Fix partial failure",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"table_name": "string", "fix_type": "string"}},
            archive={"table": "partial_fixes"},
        ),
    )

    for _i in range(3):
        h.submit_goto("2.4 Fix partial failure")
        h.submit({"table_name": f"table_{_i}", "fix_type": "alter"})

    rows = h.get_archived_rows("partial_fixes")
    assert len(rows) == 3
    assert rows[0]["table_name"] == "table_0"
    assert rows[2]["table_name"] == "table_2"


# ═══════════════════════════════════════════════════════
# Dimension tests: Error boundaries
# ═══════════════════════════════════════════════════════

def test_submit_on_waiting_fails(harness_factory):
    """Submit on a waiting step returns failure."""
    h = harness_factory("p3-db-migration.yaml")
    _walk_to_migration_review(h)
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    assert h.status == "running"

    r = h.reject("bad")
    assert not r
    assert "not waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.goto("3.1 Post-migration validation")
    h.submit({})
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.goto("3.1 Post-migration validation")
    h.submit({})
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_resume_on_running_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ═══════════════════════════════════════════════════════
# Generic / cross-cutting tests
# ═══════════════════════════════════════════════════════

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.submit({"plan": "rolling update"})

    h.save_checkpoint("at_review")

    h.approve()
    h.submit_goto("2.1 Backup database")
    assert h.step == "2.1 Backup database"

    restored = h.load_checkpoint("at_review")
    assert restored is not None
    assert restored.current_step == "1.2 Migration review"
    assert "1.1 Plan migration strategy" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    assert h.step == "1.1 Plan migration strategy"

    r = h.retry()
    assert r
    assert h.step == "1.1 Plan migration strategy"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step fails."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_back_returns_to_previous(harness_factory):
    """Back returns to the previously visited step."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.submit({})
    assert h.step == "1.2 Migration review"

    r = h.back()
    assert r
    assert h.step == "1.1 Plan migration strategy"


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p3-db-migration.yaml")

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Plan migration strategy"


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.submit({})
    assert h.step == "1.2 Migration review"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "1.2 Migration review"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"


# ═══════════════════════════════════════════════════════
# Turing machine condition checker tests
# ═══════════════════════════════════════════════════════

def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.register_node(
        "1.1 Plan migration strategy",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step.\n\n## Steps\n1. Analyze\n2. Implement",
            check=lambda data: True,
        ),
    )
    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory("p3-db-migration.yaml")
    h.start()
    h.register_node(
        "1.1 Plan migration strategy",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
