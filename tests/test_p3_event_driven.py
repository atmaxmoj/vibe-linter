"""Event-Driven Architecture workflow tests."""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# ─── Helpers ───

def _enter_event_loop(h):
    """Start -> 1.1 -> 1.2 -> enter event loop at 2.1."""
    h.start()
    h.submit({})   # 1.1 -> 1.2
    h.submit({})   # 1.2 -> 2.0 -> 2.1
    assert h.step == "2.1 Implement event handler"
    assert h.status == "running"


def _do_one_event(h):
    """Complete one event cycle: 2.1 -> 2.2 -> 2.3."""
    h.submit({})   # 2.1 -> 2.2
    h.submit({})   # 2.2 -> 2.3
    assert h.step == "2.3 Event result"


# ═══════════════════════════════════════════════════════
# Existing scenarios (unchanged)
# ═══════════════════════════════════════════════════════

def test_four_events_all_success(harness_factory):
    """Scenario 1: E-commerce order pipeline -- 4 domain events via RabbitMQ, all process successfully."""
    h = harness_factory(
        "p3-event-driven.yaml",
        loop_data={"events": [
            "order.placed",
            "payment.completed",
            "inventory.reserved",
            "shipment.dispatched",
        ]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define event schema"
    assert h.status == "running"

    # 1.1 Define CloudEvents-compatible schemas for order pipeline
    r = h.submit({
        "schema_format": "CloudEvents v1.0 + JSON Schema",
        "broker": "RabbitMQ 3.12 with quorum queues",
        "events": {
            "order.placed": {"order_id": "uuid", "customer_id": "uuid", "items": "array<OrderItem>", "total_cents": "int64"},
            "payment.completed": {"order_id": "uuid", "payment_id": "uuid", "amount_cents": "int64", "method": "enum(card,bank_transfer)"},
            "inventory.reserved": {"order_id": "uuid", "warehouse_id": "string", "items": "array<ReservedItem>"},
            "shipment.dispatched": {"order_id": "uuid", "tracking_number": "string", "carrier": "string"},
        },
        "dead_letter_exchange": "dlx.orders",
    })
    assert r
    assert r.new_step == "1.2 Design event flow"
    assert h.step == "1.2 Design event flow"

    # 1.2 Design the choreography-based saga
    r = h.submit({
        "pattern": "Choreography-based saga (no orchestrator)",
        "flow": "order.placed -> payment-service -> payment.completed -> inventory-service -> inventory.reserved -> shipping-service -> shipment.dispatched",
        "compensation": "payment.failed triggers order.canceled, inventory.release",
        "exchange_type": "topic",
        "routing_keys": "order.*, payment.*, inventory.*, shipment.*",
    })
    assert r
    assert r.new_step == "2.1 Implement event handler"
    assert h.step == "2.1 Implement event handler"

    # -- Event 1: order.placed --
    r = h.submit({
        "event": "order.placed",
        "handler": "payment_service.on_order_placed",
        "action": "Creates PaymentIntent via Stripe, publishes payment.completed on success",
        "queue": "payment.order-placed",
        "prefetch_count": 10,
    })
    assert r
    assert r.new_step == "2.2 Test event processing"
    assert h.step == "2.2 Test event processing"

    r = h.submit({
        "test": "Published order.placed to RabbitMQ, verified payment.completed emitted within 2s",
        "assertions": ["payment_id is non-null", "amount matches order total", "idempotent on retry"],
    })
    assert r
    assert r.new_step == "2.3 Event result"
    assert h.step == "2.3 Event result"

    r = h.submit_goto("2.0 Event loop")
    assert r
    assert r.new_step == "2.1 Implement event handler"
    assert h.step == "2.1 Implement event handler"

    # -- Event 2: payment.completed --
    r = h.submit({
        "event": "payment.completed",
        "handler": "inventory_service.on_payment_completed",
        "action": "Reserves stock for each item in the order, publishes inventory.reserved",
        "db": "UPDATE inventory SET reserved = reserved + $1 WHERE sku = $2 AND available >= $1",
    })
    assert r
    r = h.submit({"test": "Verified stock decremented and inventory.reserved published"})
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r
    assert r.new_step == "2.1 Implement event handler"
    assert h.step == "2.1 Implement event handler"

    # -- Event 3: inventory.reserved --
    r = h.submit({
        "event": "inventory.reserved",
        "handler": "shipping_service.on_inventory_reserved",
        "action": "Creates shipping label via EasyPost API, publishes shipment.dispatched",
    })
    assert r
    r = h.submit({"test": "Verified tracking_number generated and shipment.dispatched published"})
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r
    assert r.new_step == "2.1 Implement event handler"
    assert h.step == "2.1 Implement event handler"

    # -- Event 4: shipment.dispatched --
    r = h.submit({
        "event": "shipment.dispatched",
        "handler": "notification_service.on_shipment_dispatched",
        "action": "Sends email + push notification to customer with tracking link",
    })
    assert r
    r = h.submit({"test": "Verified email sent via SES and push via FCM"})
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r

    assert h.step == "3.1 End-to-end event flow test"

    # Verify loop_state cleaned after loop exhaustion
    assert "2.0 Event loop" not in (h.state.loop_state or {})

    # 3.1 Full saga E2E: place order -> verify all 4 events fire in sequence
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_event_lost_retry(harness_factory):
    """Scenario 2: Kafka consumer loses payment.processed events -- retry logic needed twice before adding DLQ."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["payment.processed"]})
    r = h.start()
    assert r

    r = h.submit({
        "schema_format": "Avro with Confluent Schema Registry",
        "broker": "Apache Kafka 3.6",
        "event": "payment.processed",
        "topic": "payments.processed.v1",
    })
    assert r
    r = h.submit({
        "pattern": "Consumer group with auto-commit",
        "consumer_group": "billing-service-cg",
        "partitions": 6,
    })
    assert r
    assert r.new_step == "2.1 Implement event handler"
    assert h.step == "2.1 Implement event handler"

    # Verify loop first entry
    status = h.get_status()
    assert "[1/" in status["display_path"]

    # Attempt 1: auto-commit loses events during rebalance
    r = h.submit({
        "event": "payment.processed",
        "handler": "billing_service.on_payment_processed",
        "issue": "auto.commit.interval.ms too high, events lost during consumer group rebalance",
    })
    assert r
    assert r.new_step == "2.2 Test event processing"
    assert h.step == "2.2 Test event processing"

    r = h.submit({
        "test": "Killed one consumer during processing, 3 of 10 events lost",
        "failure": "Events committed before processing completed -- at-most-once instead of at-least-once",
    })
    assert r
    assert r.new_step == "2.3 Event result"
    assert h.step == "2.3 Event result"

    r = h.submit_goto("2.1 Implement event handler")
    assert r
    assert r.new_step == "2.1 Implement event handler"
    assert h.step == "2.1 Implement event handler"

    # Attempt 2: manual commit but no idempotency -- duplicate invoices on retry
    r = h.submit({
        "event": "payment.processed",
        "fix": "Switched to manual commit after processing",
        "issue": "No idempotency key -- retry creates duplicate invoice",
    })
    assert r
    assert r.new_step == "2.2 Test event processing"
    assert h.step == "2.2 Test event processing"

    r = h.submit({
        "test": "Simulated network timeout after processing, before commit -- invoice created twice",
        "failure": "Need idempotency key in invoice creation",
    })
    assert r
    assert r.new_step == "2.3 Event result"
    assert h.step == "2.3 Event result"

    r = h.submit_goto("2.1 Implement event handler")
    assert r
    assert r.new_step == "2.1 Implement event handler"
    assert h.step == "2.1 Implement event handler"

    # Attempt 3: manual commit + idempotency key + DLQ for poison pills
    r = h.submit({
        "event": "payment.processed",
        "fix": "Manual commit + idempotency via payment_id UNIQUE constraint + DLQ after 3 retries",
        "config": {"enable.auto.commit": False, "max.poll.records": 100, "max.retries": 3},
    })
    assert r
    r = h.submit({
        "test": "10k events processed with chaos testing (kill consumer, network partition) -- zero loss, zero duplicates",
        "result": "pass",
    })
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r
    assert h.step == "3.1 End-to-end event flow test"


def test_design_flawed_cross_phase_back(harness_factory):
    """Scenario 3: Event schema fundamentally flawed -- fan-out creates infinite loop, must redesign from scratch."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["user.activity.tracked"]})
    r = h.start()
    assert r

    r = h.submit({
        "schema_format": "JSON Schema",
        "broker": "RabbitMQ",
        "event": "user.activity.tracked",
        "flaw": "Activity tracking event triggers notification, which triggers another activity event -- infinite loop",
    })
    assert r
    r = h.submit({
        "pattern": "Fan-out exchange with topic routing",
        "problem": "notification.sent re-publishes to user.activity exchange, creating cycle",
    })
    assert r
    r = h.submit({
        "event": "user.activity.tracked",
        "handler": "analytics_service.track",
        "issue": "Handler publishes notification.sent which loops back to activity tracking",
    })
    assert r
    r = h.submit({
        "test": "Published 1 activity event, observed 500+ messages in 10 seconds -- infinite loop confirmed",
    })
    assert r
    assert h.step == "2.3 Event result"

    # Design is fundamentally flawed -- go back to schema definition
    r = h.submit_goto("1.1 Define event schema")
    assert r
    assert r.new_step == "1.1 Define event schema"
    assert h.step == "1.1 Define event schema"
    assert h.status == "running"

    # Redesign: separate internal vs external events to break the cycle
    r = h.submit({
        "schema_format": "JSON Schema",
        "fix": "Split into internal (system.activity) and external (user.activity) events, internal events cannot trigger notifications",
        "event": "user.activity.tracked (external only, no fan-out to notification exchange)",
    })
    assert r
    r = h.submit({
        "pattern": "Separate exchanges: user-events (external) and system-events (internal, no notification binding)",
    })
    assert r

    assert h.step == "3.1 End-to-end event flow test"

    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_e2e_fails_back_to_loop(harness_factory):
    """Scenario 4: E2E test fails -- order.created and payment.charged work individually but race condition in E2E flow."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["order.created", "payment.charged"]})
    r = h.start()
    assert r

    r = h.submit({
        "schema_format": "CloudEvents v1.0",
        "broker": "Amazon SQS + SNS",
        "events": ["order.created", "payment.charged"],
    })
    assert r
    r = h.submit({
        "pattern": "SNS fan-out to SQS queues",
        "topics": ["order-events", "payment-events"],
    })
    assert r
    assert h.step == "2.1 Implement event handler"

    # Implement both event handlers
    r = h.submit({"event": "order.created", "handler": "payment_service.initiate_charge", "sqs_queue": "payment-order-created"})
    assert r
    r = h.submit({"test": "order.created processed in isolation -- payment initiated successfully"})
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r

    r = h.submit({"event": "payment.charged", "handler": "fulfillment_service.start_fulfillment", "sqs_queue": "fulfillment-payment-charged"})
    assert r
    r = h.submit({"test": "payment.charged processed in isolation -- fulfillment started"})
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r

    assert h.step == "3.1 End-to-end event flow test"

    # E2E fails: payment.charged arrives before order.created is fully persisted (race condition)
    r = h.submit_goto("2.0 Event loop")
    assert r
    assert r.new_step == "2.1 Implement event handler"
    assert h.step == "2.1 Implement event handler"
    assert h.status == "running"

    # Fix: add SQS visibility timeout + order existence check with exponential backoff
    r = h.submit({
        "event": "order.created",
        "fix": "Added SQS visibility timeout of 30s and deduplication via order_id",
    })
    assert r
    r = h.submit({"test": "Verified at-least-once delivery with deduplication"})
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r

    r = h.submit({
        "event": "payment.charged",
        "fix": "Added retry with exponential backoff if order not found (max 3 retries, 1s/2s/4s)",
    })
    assert r
    r = h.submit({"test": "Verified handler waits for order to exist before starting fulfillment"})
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r

    assert h.step == "3.1 End-to-end event flow test"

    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_stop_then_resume(harness_factory):
    """Scenario 5: Stop during Kafka handler implementation -- Confluent cluster undergoing maintenance window."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["audit.log.created"]})
    r = h.start()
    assert r

    r = h.submit({
        "schema_format": "Avro",
        "broker": "Confluent Cloud Kafka",
        "event": "audit.log.created",
        "topic": "audit-logs-v1",
    })
    assert r
    r = h.submit({
        "pattern": "Single consumer with compacted topic for audit trail",
        "retention": "infinite (compacted)",
    })
    assert r
    assert r.new_step == "2.1 Implement event handler"
    assert h.step == "2.1 Implement event handler"

    # Stop: Confluent Cloud cluster maintenance window
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.1 Implement event handler"

    # Maintenance complete -- resume
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.1 Implement event handler"

    r = h.submit({
        "event": "audit.log.created",
        "handler": "compliance_service.persist_audit_log",
        "storage": "PostgreSQL audit_logs table with JSONB payload column",
    })
    assert r
    r = h.submit({"test": "Verified audit log persisted with correct timestamp and actor_id"})
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_skip_event(harness_factory):
    """Scenario 6: Skip testing for user.login event -- handler migrated from legacy system, already battle-tested."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["user.login", "user.logout"]})
    r = h.start()
    assert r

    r = h.submit({
        "schema_format": "JSON Schema",
        "broker": "Redis Streams",
        "events": ["user.login", "user.logout"],
    })
    assert r
    r = h.submit({"pattern": "Consumer group per service via XREADGROUP"})
    assert r
    r = h.submit({
        "event": "user.login",
        "handler": "session_service.on_login",
        "note": "Migrated from legacy system -- handler logic unchanged, already processing 1M events/day",
    })
    assert r
    assert r.new_step == "2.2 Test event processing"
    assert h.step == "2.2 Test event processing"

    # Skip testing for migrated handler
    r = h.skip("Handler migrated from production -- 1M events/day for 2 years, no changes to logic")
    assert r
    assert r.new_step == "2.3 Event result"
    assert h.step == "2.3 Event result"

    r = h.submit_goto("2.0 Event loop")
    assert r
    r = h.submit({"event": "user.logout", "handler": "session_service.on_logout", "action": "Invalidates session token in Redis"})
    assert r
    r = h.submit({"test": "Verified session key deleted from Redis after logout event"})
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r

    assert h.step == "3.1 End-to-end event flow test"

    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_complete_then_reset(harness_factory):
    """Scenario 7: Ship CQRS read-model sync v1, reset to redesign with event sourcing for v2."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["product.updated"]})
    r = h.start()
    assert r

    r = h.submit({
        "schema_format": "CloudEvents v1.0",
        "broker": "Amazon EventBridge",
        "event": "product.updated",
        "purpose": "Sync product catalog read-model in Elasticsearch",
    })
    assert r
    r = h.submit({
        "pattern": "CQRS: write to PostgreSQL, async project to Elasticsearch via EventBridge",
    })
    assert r
    r = h.submit({
        "event": "product.updated",
        "handler": "search_projector.update_product_index",
        "target": "Elasticsearch products index, denormalized with category and brand names",
    })
    assert r
    r = h.submit({"test": "Updated product name in PG, verified ES index reflects change within 500ms"})
    assert r
    r = h.submit_goto("2.0 Event loop")
    assert r
    r = h.submit_goto("Done")
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # v1 shipped
    r = h.submit({})
    assert not r

    # Reset to redesign with full event sourcing for v2
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define event schema"
    assert h.status == "running"


def test_empty_event_list(harness_factory):
    """Scenario 8: Infrastructure-only setup -- define schemas and flow but no events to implement yet."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": []})
    r = h.start()
    assert r

    r = h.submit({
        "schema_format": "Avro",
        "broker": "Kafka",
        "note": "Setting up Kafka topics and schema registry -- event handlers will be added in sprint 8",
        "topics_created": ["orders.v1", "payments.v1", "inventory.v1"],
    })
    assert r
    r = h.submit({
        "pattern": "Topic partitioning strategy: partition by tenant_id for multi-tenant isolation",
        "partitions_per_topic": 12,
    })
    assert r

    assert h.step == "3.1 End-to-end event flow test"
    assert h.status == "running"


def test_goto(harness_factory):
    """Scenario 9: Jump to E2E test -- event handlers already deployed, need to verify the full NATS JetStream flow."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["task.assigned", "task.completed"]})
    r = h.start()
    assert r

    r = h.submit({
        "schema_format": "CloudEvents v1.0",
        "broker": "NATS JetStream",
        "events": ["task.assigned", "task.completed"],
        "note": "Handlers already deployed in staging -- jump to E2E verification",
    })
    assert r
    r = h.submit({
        "pattern": "JetStream pull consumers with durable subscriptions",
        "stream": "TASKS",
        "subjects": ["task.>"],
    })
    assert r

    # Skip individual handler work -- jump to E2E
    r = h.goto("3.1 End-to-end event flow test")
    assert r
    assert r.new_step == "3.1 End-to-end event flow test"
    assert h.step == "3.1 End-to-end event flow test"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_modify_yaml_add_monitoring(harness_factory):
    """Scenario 10: Hot-reload YAML to add Datadog event monitoring step after observability review."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["invoice.generated"]})
    r = h.start()
    assert r

    r = h.submit({
        "schema_format": "Avro",
        "broker": "Kafka",
        "event": "invoice.generated",
        "note": "SRE team requires observability setup before implementing handlers",
    })
    assert r
    assert r.new_step == "1.2 Design event flow"
    assert h.step == "1.2 Design event flow"

    # SRE team requires monitoring step -- hot-reload YAML
    yaml_content = """名称: Event-Driven Architecture
描述: Event loop, 3-way (success/retry/redesign), cross-phase fallback to definition

步骤:
  - 1.1 Define event schema

  - 1.2 Design event flow

  - 1.3 Setup event monitoring

  - 2.0 Event loop:
      遍历: "events"
      子步骤:
        - 2.1 Implement event handler
        - 2.2 Test event processing
        - 2.3 Event result:
            下一步:
              - 如果: "event processes successfully"
                去: 2.0 Event loop
              - 如果: "event lost or failed, needs retry logic"
                去: 2.1 Implement event handler
              - 如果: "event design is fundamentally flawed"
                去: 1.1 Define event schema

  - 3.1 End-to-end event flow test:
      下一步:
        - 如果: "all events flow correctly end to end"
          去: Done
        - 去: 2.0 Event loop

  - Done:
      类型: terminate
      原因: Event-driven architecture verified
"""
    h.reload_yaml(yaml_content)

    r = h.goto("1.3 Setup event monitoring")
    assert r
    assert r.new_step == "1.3 Setup event monitoring"
    assert h.step == "1.3 Setup event monitoring"
    assert h.status == "running"

    # Setup Datadog monitoring for Kafka consumer lag and DLQ depth
    r = h.submit({
        "tool": "Datadog APM + Kafka integration",
        "monitors": [
            "kafka.consumer_lag > 10000 for 5m -> PagerDuty P2",
            "kafka.dlq.message_count > 0 -> Slack #alerts",
            "event.processing.duration.p99 > 5s -> PagerDuty P3",
        ],
        "dashboard": "Event Processing SLOs -- throughput, latency, error rate",
    })
    assert r
    assert r.new_step == "2.1 Implement event handler"
    assert h.step == "2.1 Implement event handler"


# ═══════════════════════════════════════════════════════
# Dimension tests: Data accumulation
# ═══════════════════════════════════════════════════════

def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()

    h.submit({"schema": "event_v1"})
    data = h.state.data
    assert "1.1 Define event schema" in data
    assert data["1.1 Define event schema"]["schema"] == "event_v1"

    h.submit({"flow": "pub-sub"})
    data = h.state.data
    assert "1.2 Design event flow" in data
    assert data["1.2 Design event flow"]["flow"] == "pub-sub"


def test_s2_data_after_retry(harness_factory):
    """Data persists after retry loop back to handler."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    _enter_event_loop(h)

    h.submit({"handler": "v1"})
    h.submit({})
    h.submit_goto("2.1 Implement event handler")

    h.submit({"handler": "v2"})
    data = h.state.data
    assert data["2.1 Implement event handler"]["handler"] == "v2"


# ═══════════════════════════════════════════════════════
# Dimension tests: History audit trail
# ═══════════════════════════════════════════════════════

def test_s1_history_audit_trail(harness_factory):
    """After walkthrough, history contains expected action sequence."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Event loop")
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_s3_history_cross_phase(harness_factory):
    """History records cross-phase goto back to definition."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    _enter_event_loop(h)
    _do_one_event(h)
    h.submit_goto("1.1 Define event schema")

    history = h.get_history(30)
    actions = [e["action"] for e in history]
    assert "submit" in actions


# ═══════════════════════════════════════════════════════
# Dimension tests: Cross-executor recovery
# ═══════════════════════════════════════════════════════

def test_cross_executor_at_design(harness_factory):
    """Close at design flow, reopen, state persists."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Design event flow"

    h.new_executor()

    assert h.step == "1.2 Design event flow"
    assert h.status == "running"


def test_cross_executor_mid_loop(harness_factory):
    """Close mid-loop, reopen, loop state preserved."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1", "e2"]})
    _enter_event_loop(h)

    h.submit({"handler": "v1"})
    assert h.step == "2.2 Test event processing"

    h.new_executor()

    assert h.step == "2.2 Test event processing"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Event loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    h.goto("3.1 End-to-end event flow test")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


# ═══════════════════════════════════════════════════════
# Dimension tests: Node validation
# ═══════════════════════════════════════════════════════

def test_node_validates_handler(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    _enter_event_loop(h)

    h.register_node(
        "2.1 Implement event handler",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("handler") else "must include handler",
        ),
    )

    r = h.submit({"notes": "no handler"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"handler": "on_order_created"})
    assert r
    assert r.new_step == "2.2 Test event processing"


def test_node_validates_schema(harness_factory):
    """Validate node on schema definition step."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()

    h.register_node(
        "1.1 Define event schema",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("events") else "must list events",
        ),
    )

    r = h.submit({"description": "no events"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"events": ["order.created"]})
    assert r


# ═══════════════════════════════════════════════════════
# Dimension tests: Node archival
# ═══════════════════════════════════════════════════════

def test_node_archives_handlers(harness_factory):
    """Archive node writes each handler to SQLite."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1", "e2"]})
    _enter_event_loop(h)

    h.register_node(
        "2.1 Implement event handler",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"name": "string", "event_type": "string"}},
            archive={"table": "event_handlers"},
        ),
    )

    for _i in range(2):
        h.submit({"name": f"handler_{_i}", "event_type": "domain"})
        h.submit({})
        h.submit_goto("2.0 Event loop")

    rows = h.get_archived_rows("event_handlers")
    assert len(rows) == 2
    assert rows[0]["name"] == "handler_0"
    assert rows[1]["name"] == "handler_1"


# ═══════════════════════════════════════════════════════
# Dimension tests: Error boundaries
# ═══════════════════════════════════════════════════════

def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    assert h.status == "running"

    r = h.reject("bad")
    assert not r
    assert "not waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    h.goto("3.1 End-to-end event flow test")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    h.goto("3.1 End-to-end event flow test")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_resume_on_running_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ═══════════════════════════════════════════════════════
# Generic / cross-cutting tests
# ═══════════════════════════════════════════════════════

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    h.submit({"schema": "event_v1"})

    h.save_checkpoint("at_design")

    h.submit({})
    assert h.step == "2.1 Implement event handler"

    restored = h.load_checkpoint("at_design")
    assert restored is not None
    assert restored.current_step == "1.2 Design event flow"
    assert "1.1 Define event schema" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    assert h.step == "1.1 Define event schema"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define event schema"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step fails."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_back_returns_to_previous(harness_factory):
    """Back returns to the previously visited step."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Design event flow"

    r = h.back()
    assert r
    assert h.step == "1.1 Define event schema"


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define event schema"


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["a", "b", "c"]})
    _enter_event_loop(h)

    loop_info = h.state.loop_state["2.0 Event loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_event(h)
    h.submit_goto("2.0 Event loop")

    loop_info = h.state.loop_state["2.0 Event loop"]
    assert loop_info["i"] == 1


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["e1"]})
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "2.1 Implement event handler"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "2.1 Implement event handler"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"


# ═══════════════════════════════════════════════════════
# Turing machine condition checker tests
# ═══════════════════════════════════════════════════════

def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["order.placed"]})
    h.start()
    h.register_node(
        "1.1 Define event schema",
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
    h = harness_factory("p3-event-driven.yaml", loop_data={"events": ["order.placed"]})
    h.start()
    h.register_node(
        "1.1 Define event schema",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
