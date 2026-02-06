"""Hexagonal Architecture workflow tests."""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# ─── Helpers ───

def _walk_to_domain_review(h):
    """Start -> submit 1.1 -> arrive at 1.2 Domain review (waiting)."""
    h.start()
    h.submit({})
    assert h.step == "1.2 Domain review"
    assert h.status == "waiting"


def _enter_port_loop(h):
    """Get past domain review into port loop at 2.1."""
    _walk_to_domain_review(h)
    h.approve()
    h.submit_goto("2.0 Port loop")
    assert h.step == "2.1 Define port interface"
    assert h.status == "running"


def _do_one_port(h):
    """Complete one port cycle: 2.1 -> 2.2 -> 2.3."""
    h.submit({})   # 2.1 -> 2.2
    h.submit({})   # 2.2 -> 2.3
    assert h.step == "2.3 Adapter test"


# ═══════════════════════════════════════════════════════
# Existing scenarios (unchanged)
# ═══════════════════════════════════════════════════════

def test_five_ports_complete(harness_factory):
    """Scenario 1: Order management service with 5 ports -- REST, PostgreSQL, Redis, Kafka, S3."""
    h = harness_factory(
        "p3-hexagonal.yaml",
        loop_data={"ports": [
            "OrderRepositoryPort",
            "PaymentGatewayPort",
            "CachePort",
            "EventPublisherPort",
            "FileStoragePort",
        ]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Design domain model"
    assert h.status == "running"

    # 1.1 Design the domain model with DDD aggregates
    r = h.submit({
        "aggregates": {
            "Order": {"root": True, "entities": ["OrderItem", "ShippingAddress"], "value_objects": ["Money", "OrderStatus"]},
            "Customer": {"root": True, "value_objects": ["Email", "CustomerTier"]},
        },
        "domain_events": ["OrderPlaced", "OrderPaid", "OrderShipped", "OrderCanceled"],
        "invariants": [
            "Order total must be positive",
            "Cannot cancel a shipped order",
            "Premium customers get free shipping over $50",
        ],
    })
    assert r
    assert r.new_step == "1.2 Domain review"
    assert h.step == "1.2 Domain review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Port loop")
    assert r
    assert r.new_step == "2.1 Define port interface"
    assert h.step == "2.1 Define port interface"

    # -- Port 1: OrderRepositoryPort (driven/outbound) --
    r = h.submit({
        "port": "OrderRepositoryPort",
        "direction": "outbound (driven)",
        "interface": "save(order), find_by_id(id), find_by_customer(customer_id, pagination)",
        "note": "Abstract persistence -- domain does not know about SQL",
    })
    assert r
    assert r.new_step == "2.2 Implement adapter"
    assert h.step == "2.2 Implement adapter"

    r = h.submit({
        "adapter": "PostgresOrderRepository",
        "implementation": "SQLAlchemy ORM with Order/OrderItem mappers, uses SERIALIZABLE isolation for concurrent updates",
        "db": "CREATE TABLE orders (id UUID PRIMARY KEY, customer_id UUID, status VARCHAR, total_cents BIGINT)",
    })
    assert r
    assert r.new_step == "2.3 Adapter test"
    assert h.step == "2.3 Adapter test"

    r = h.submit_goto("2.0 Port loop")
    assert r
    assert r.new_step == "2.1 Define port interface"
    assert h.step == "2.1 Define port interface"

    # -- Port 2: PaymentGatewayPort --
    r = h.submit({
        "port": "PaymentGatewayPort",
        "direction": "outbound (driven)",
        "interface": "charge(order_id, amount: Money) -> PaymentResult",
    })
    assert r
    r = h.submit({
        "adapter": "StripePaymentAdapter",
        "implementation": "stripe.PaymentIntent.create with idempotency_key=order_id",
    })
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r
    assert r.new_step == "2.1 Define port interface"
    assert h.step == "2.1 Define port interface"

    # -- Port 3: CachePort --
    r = h.submit({
        "port": "CachePort",
        "direction": "outbound (driven)",
        "interface": "get(key), set(key, value, ttl), invalidate(key)",
    })
    assert r
    r = h.submit({
        "adapter": "RedisCacheAdapter",
        "implementation": "redis-py with connection pooling, JSON serialization, 5min default TTL",
    })
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r
    assert r.new_step == "2.1 Define port interface"
    assert h.step == "2.1 Define port interface"

    # -- Port 4: EventPublisherPort --
    r = h.submit({
        "port": "EventPublisherPort",
        "direction": "outbound (driven)",
        "interface": "publish(domain_event: DomainEvent)",
    })
    assert r
    r = h.submit({
        "adapter": "KafkaEventPublisher",
        "implementation": "confluent-kafka producer with Avro serialization, partition by order_id",
    })
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r
    assert r.new_step == "2.1 Define port interface"
    assert h.step == "2.1 Define port interface"

    # -- Port 5: FileStoragePort --
    r = h.submit({
        "port": "FileStoragePort",
        "direction": "outbound (driven)",
        "interface": "upload(key, content), get_presigned_url(key, expires_in)",
    })
    assert r
    r = h.submit({
        "adapter": "S3FileStorageAdapter",
        "implementation": "boto3 S3 client with multipart upload for invoices > 5MB",
    })
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r

    assert h.step == "3.1 End-to-end testing"

    # Verify loop_state cleaned after loop exhaustion
    assert "2.0 Port loop" not in (h.state.loop_state or {})

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_adapter_test_fails(harness_factory):
    """Scenario 2: PostgreSQL repository adapter fails 3 times -- connection pool exhaustion, transaction isolation, N+1 query."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["OrderRepositoryPort"]})
    r = h.start()
    assert r

    r = h.submit({
        "aggregates": {"Order": {"root": True, "entities": ["OrderItem"]}},
        "domain_events": ["OrderPlaced"],
    })
    assert r
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Port loop")
    assert r
    assert r.new_step == "2.1 Define port interface"
    assert h.step == "2.1 Define port interface"

    # Verify loop first entry
    status = h.get_status()
    assert "[1/" in status["display_path"]

    # Define port interface
    r = h.submit({
        "port": "OrderRepositoryPort",
        "interface": "save(order), find_by_id(id), find_by_customer(customer_id)",
    })
    assert r
    assert r.new_step == "2.2 Implement adapter"
    assert h.step == "2.2 Implement adapter"

    # Attempt 1: connection pool exhaustion under load
    r = h.submit({
        "adapter": "PostgresOrderRepository",
        "issue": "Connection pool (size=5) exhausted under 50 concurrent requests -- asyncpg pool too small",
    })
    assert r
    assert r.new_step == "2.3 Adapter test"
    assert h.step == "2.3 Adapter test"

    r = h.submit_goto("2.2 Implement adapter")
    assert r
    assert r.new_step == "2.2 Implement adapter"
    assert h.step == "2.2 Implement adapter"

    # Attempt 2: increased pool but wrong transaction isolation
    r = h.submit({
        "fix": "Increased pool to min=10, max=50",
        "issue": "READ COMMITTED allows dirty reads -- concurrent order updates cause lost writes",
    })
    assert r
    assert r.new_step == "2.3 Adapter test"
    assert h.step == "2.3 Adapter test"

    r = h.submit_goto("2.2 Implement adapter")
    assert r
    assert r.new_step == "2.2 Implement adapter"
    assert h.step == "2.2 Implement adapter"

    # Attempt 3: fixed isolation but N+1 on order items
    r = h.submit({
        "fix": "Switched to SERIALIZABLE isolation for order mutations",
        "issue": "find_by_customer executes N+1 queries -- 1 for orders + 1 per order for items",
    })
    assert r
    assert r.new_step == "2.3 Adapter test"
    assert h.step == "2.3 Adapter test"

    r = h.submit_goto("2.2 Implement adapter")
    assert r
    assert r.new_step == "2.2 Implement adapter"
    assert h.step == "2.2 Implement adapter"

    # Attempt 4: all issues fixed
    r = h.submit({
        "fix": "Added selectinload(Order.items) to eliminate N+1, pool=50, SERIALIZABLE for writes",
        "all_tests_pass": True,
    })
    assert r
    assert r.new_step == "2.3 Adapter test"
    assert h.step == "2.3 Adapter test"

    r = h.submit_goto("2.0 Port loop")
    assert r
    assert h.step == "3.1 End-to-end testing"


def test_domain_review_rejected(harness_factory):
    """Scenario 3: Domain model rejected -- anemic model with business logic in services instead of aggregates."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["NotificationPort"]})
    r = h.start()
    assert r

    # First attempt: anemic domain model
    r = h.submit({
        "aggregates": {
            "Notification": {"root": True, "fields": ["id", "user_id", "message", "sent"]},
        },
        "problem": "Anemic model: all business rules (rate limiting, dedup, channel routing) live in NotificationService, not the aggregate",
    })
    assert r
    assert r.new_step == "1.2 Domain review"
    assert h.step == "1.2 Domain review"
    assert h.status == "waiting"

    # Rejected: domain logic must live in aggregates per DDD principles
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("1.1 Design domain model")
    assert r
    assert r.new_step == "1.1 Design domain model"
    assert h.step == "1.1 Design domain model"
    assert h.status == "running"

    # Redesign: rich domain model with behavior in aggregates
    r = h.submit({
        "aggregates": {
            "NotificationRequest": {
                "root": True,
                "entities": ["DeliveryAttempt"],
                "value_objects": ["Channel", "Priority", "RateLimit"],
                "behavior": [
                    "send() -- applies rate limit, selects channel, creates DeliveryAttempt",
                    "retry() -- exponential backoff, max 3 attempts",
                    "suppress_duplicate() -- dedup by content hash within 5min window",
                ],
            },
        },
        "domain_events": ["NotificationSent", "NotificationFailed", "NotificationSuppressed"],
    })
    assert r
    assert r.new_step == "1.2 Domain review"
    assert h.step == "1.2 Domain review"

    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Port loop")
    assert r
    assert r.new_step == "2.1 Define port interface"
    assert h.step == "2.1 Define port interface"


def test_e2e_fails_back_to_port_loop(harness_factory):
    """Scenario 4: E2E fails -- Redis cache adapter returns stale data after PostgreSQL write, cache invalidation bug."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["RepositoryPort", "CachePort"]})
    r = h.start()
    assert r

    r = h.submit({
        "aggregates": {"Product": {"root": True, "fields": ["id", "name", "price_cents", "stock"]}},
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r
    assert h.step == "2.1 Define port interface"

    # Port 1: RepositoryPort
    r = h.submit({"port": "RepositoryPort", "interface": "save(product), find_by_id(id)"})
    assert r
    r = h.submit({"adapter": "PostgresProductRepository", "implementation": "SQLAlchemy with asyncpg"})
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r

    # Port 2: CachePort
    r = h.submit({"port": "CachePort", "interface": "get(key), set(key, value, ttl), invalidate(key)"})
    assert r
    r = h.submit({"adapter": "RedisCacheAdapter", "implementation": "redis-py with 5min TTL"})
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r

    assert h.step == "3.1 End-to-end testing"

    # E2E fails: update product price in PG, but Redis still serves old price
    r = h.submit_goto("2.0 Port loop")
    assert r
    assert r.new_step == "2.1 Define port interface"
    assert h.step == "2.1 Define port interface"
    assert h.status == "running"

    # Fix both adapters: add cache-aside pattern with write-through invalidation
    r = h.submit({"port": "RepositoryPort", "fix": "Added post-save hook that publishes cache invalidation event"})
    assert r
    r = h.submit({"adapter": "PostgresProductRepository", "fix": "save() now calls cache.invalidate(f'product:{id}') after commit"})
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r

    r = h.submit({"port": "CachePort", "fix": "Added write-through: set() called after invalidate on next read"})
    assert r
    r = h.submit({"adapter": "RedisCacheAdapter", "fix": "invalidate() uses DEL + pub/sub to notify other instances"})
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r

    assert h.step == "3.1 End-to-end testing"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_stop_then_resume(harness_factory):
    """Scenario 5: Stop during domain review -- waiting for DDD modeling workshop with the team."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["SearchPort"]})
    r = h.start()
    assert r

    r = h.submit({
        "aggregates": {
            "SearchQuery": {"root": True, "value_objects": ["SearchFilter", "SortCriteria", "Pagination"]},
        },
        "note": "Waiting for event storming workshop to validate bounded context boundaries",
    })
    assert r
    assert r.new_step == "1.2 Domain review"
    assert h.step == "1.2 Domain review"

    # Stop: team workshop scheduled for next week
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "1.2 Domain review"

    # Workshop complete -- resume with validated model
    r = h.resume()
    assert r
    assert h.status == "waiting"
    assert h.step == "1.2 Domain review"

    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Port loop")
    assert r
    assert r.new_step == "2.1 Define port interface"
    assert h.step == "2.1 Define port interface"


def test_skip_port(harness_factory):
    """Scenario 6: Skip email adapter implementation -- using existing SendGrid adapter from shared library."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["EmailPort", "SmsPort"]})
    r = h.start()
    assert r

    r = h.submit({
        "aggregates": {"Notification": {"root": True, "entities": ["DeliveryAttempt"]}},
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r

    # Port 1: EmailPort -- skip adapter, already exists in shared lib
    r = h.submit({
        "port": "EmailPort",
        "interface": "send(to, subject, body_html)",
        "note": "Adapter exists in @acme/email-adapter package",
    })
    assert r
    assert r.new_step == "2.2 Implement adapter"
    assert h.step == "2.2 Implement adapter"

    r = h.skip("Using existing SendGridEmailAdapter from @acme/email-adapter v2.3.1")
    assert r
    assert r.new_step == "2.3 Adapter test"
    assert h.step == "2.3 Adapter test"

    r = h.submit_goto("2.0 Port loop")
    assert r

    # Port 2: SmsPort -- implement from scratch
    r = h.submit({"port": "SmsPort", "interface": "send(phone_number, message)"})
    assert r
    r = h.submit({"adapter": "TwilioSmsAdapter", "implementation": "twilio-python SDK with retry on 429"})
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r

    assert h.step == "3.1 End-to-end testing"

    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_complete_then_reset(harness_factory):
    """Scenario 7: Ship user service v1 with PostgreSQL, reset for v2 migration to DynamoDB."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["UserRepositoryPort"]})
    r = h.start()
    assert r

    r = h.submit({
        "aggregates": {"User": {"root": True, "value_objects": ["Email", "HashedPassword"]}},
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r
    r = h.submit({"port": "UserRepositoryPort", "interface": "save(user), find_by_email(email)"})
    assert r
    r = h.submit({"adapter": "PostgresUserRepository", "implementation": "asyncpg with bcrypt password hashing"})
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r
    r = h.submit_goto("Done")
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    r = h.submit({})
    assert not r

    # Reset for v2: swap PostgreSQL adapter for DynamoDB (hexagonal makes this easy)
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Design domain model"
    assert h.status == "running"


def test_empty_port_list(harness_factory):
    """Scenario 8: Domain model review only -- pure domain logic with no external dependencies yet."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": []})
    r = h.start()
    assert r

    r = h.submit({
        "aggregates": {
            "PricingRule": {
                "root": True,
                "value_objects": ["Discount", "TierThreshold"],
                "behavior": ["calculate_price(base_price, customer_tier, quantity)"],
            },
        },
        "note": "Pure domain logic -- no ports needed yet, testing domain rules in isolation",
    })
    assert r
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Port loop")
    assert r

    assert h.step == "3.1 End-to-end testing"
    assert h.status == "running"


def test_goto(harness_factory):
    """Scenario 9: Jump to E2E testing -- adapters already implemented in previous sprint, validating wiring only."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["MetricsPort", "LoggingPort"]})
    r = h.start()
    assert r

    r = h.submit({
        "aggregates": {"RequestContext": {"root": True, "value_objects": ["TraceId", "SpanId"]}},
        "note": "Observability ports -- adapters built in sprint 7, just need E2E wiring test",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r

    # Skip to E2E -- adapters already exist
    r = h.goto("3.1 End-to-end testing")
    assert r
    assert r.new_step == "3.1 End-to-end testing"
    assert h.step == "3.1 End-to-end testing"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_back(harness_factory):
    """Scenario 10: Go back to revise domain model after realizing Wallet aggregate needs new invariant."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["WalletRepositoryPort"]})
    r = h.start()
    assert r

    r = h.submit({
        "aggregates": {"Wallet": {"root": True, "value_objects": ["Balance", "Currency"]}},
    })
    assert r
    assert r.new_step == "1.2 Domain review"
    assert h.step == "1.2 Domain review"

    # Realized we need a daily withdrawal limit invariant -- go back
    r = h.back()
    assert r
    assert r.new_step == "1.1 Design domain model"
    assert h.step == "1.1 Design domain model"
    assert h.status == "running"

    r = h.submit({
        "aggregates": {
            "Wallet": {
                "root": True,
                "value_objects": ["Balance", "Currency", "DailyWithdrawalLimit"],
                "invariants": ["Balance cannot go negative", "Daily withdrawals cannot exceed limit"],
            },
        },
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r
    r = h.submit({"port": "WalletRepositoryPort", "interface": "save(wallet), find_by_user_id(user_id)"})
    assert r

    # Back to revise port interface -- need to add find_with_daily_totals
    r = h.back()
    assert r
    assert r.new_step == "2.1 Define port interface"
    assert h.step == "2.1 Define port interface"

    r = h.submit({"port": "WalletRepositoryPort", "interface": "save(wallet), find_by_user_id(user_id), find_with_daily_totals(user_id, date)"})
    assert r
    r = h.submit({"adapter": "PostgresWalletRepository", "implementation": "SUM(amount) for daily totals with date index"})
    assert r
    r = h.submit_goto("2.0 Port loop")
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


# ═══════════════════════════════════════════════════════
# Dimension tests: Data accumulation
# ═══════════════════════════════════════════════════════

def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()

    h.submit({"model": "DDD aggregates"})
    data = h.state.data
    assert "1.1 Design domain model" in data
    assert data["1.1 Design domain model"]["model"] == "DDD aggregates"

    h.approve()
    h.submit_goto("2.0 Port loop")
    h.submit({"port": "OrderPort"})
    data = h.state.data
    assert "2.1 Define port interface" in data
    assert data["2.1 Define port interface"]["port"] == "OrderPort"


def test_s2_data_after_adapter_retry(harness_factory):
    """Data persists after adapter retry loop."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    _enter_port_loop(h)

    h.submit({})
    h.submit({"adapter": "v1"})
    h.submit_goto("2.2 Implement adapter")
    h.submit({"adapter": "v2"})
    data = h.state.data
    assert data["2.2 Implement adapter"]["adapter"] == "v2"


# ═══════════════════════════════════════════════════════
# Dimension tests: History audit trail
# ═══════════════════════════════════════════════════════

def test_s1_history_audit_trail(harness_factory):
    """After walkthrough, history contains expected action sequence."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    h.submit({})
    h.approve()
    h.submit_goto("2.0 Port loop")
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Port loop")
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "approve" in actions
    assert "submit" in actions
    assert "terminate" in actions[-1]


def test_s3_history_shows_reject_path(harness_factory):
    """History records the reject path through domain review."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    h.submit({})
    h.approve()
    h.submit_goto("1.1 Design domain model")

    history = h.get_history(20)
    actions = [e["action"] for e in history]
    assert "approve" in actions
    assert "submit" in actions


# ═══════════════════════════════════════════════════════
# Dimension tests: Cross-executor recovery
# ═══════════════════════════════════════════════════════

def test_cross_executor_at_domain_review(harness_factory):
    """Close at domain review, reopen, state persists."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    _walk_to_domain_review(h)

    h.new_executor()

    assert h.step == "1.2 Domain review"
    assert h.status == "waiting"

    h.approve()
    r = h.submit_goto("2.0 Port loop")
    assert r
    assert h.step == "2.1 Define port interface"


def test_cross_executor_mid_loop(harness_factory):
    """Close mid-loop, reopen, loop state preserved."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1", "p2"]})
    _enter_port_loop(h)

    h.submit({"port": "OrderPort"})
    assert h.step == "2.2 Implement adapter"

    h.new_executor()

    assert h.step == "2.2 Implement adapter"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Port loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    h.goto("3.1 End-to-end testing")
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

def test_node_validates_port(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    _enter_port_loop(h)

    h.register_node(
        "2.1 Define port interface",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("port") else "must include port name",
        ),
    )

    r = h.submit({"notes": "no port"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"port": "OrderPort"})
    assert r
    assert r.new_step == "2.2 Implement adapter"


def test_node_validates_domain(harness_factory):
    """Validate node on domain model step."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()

    h.register_node(
        "1.1 Design domain model",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("entities") else "must list entities",
        ),
    )

    r = h.submit({"description": "no entities"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"entities": ["Order", "Product"]})
    assert r


# ═══════════════════════════════════════════════════════
# Dimension tests: Node archival
# ═══════════════════════════════════════════════════════

def test_node_archives_ports(harness_factory):
    """Archive node writes each port to SQLite."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1", "p2"]})
    _enter_port_loop(h)

    h.register_node(
        "2.1 Define port interface",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"name": "string", "direction": "string"}},
            archive={"table": "port_definitions"},
        ),
    )

    for _i in range(2):
        h.submit({"name": f"port_{_i}", "direction": "inbound"})
        h.submit({})
        h.submit_goto("2.0 Port loop")

    rows = h.get_archived_rows("port_definitions")
    assert len(rows) == 2
    assert rows[0]["name"] == "port_0"
    assert rows[1]["name"] == "port_1"


# ═══════════════════════════════════════════════════════
# Dimension tests: Error boundaries
# ═══════════════════════════════════════════════════════

def test_submit_on_waiting_fails(harness_factory):
    """Submit on a waiting step returns failure."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    _walk_to_domain_review(h)
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    assert h.status == "running"

    r = h.reject("bad")
    assert not r
    assert "not waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    h.goto("3.1 End-to-end testing")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    h.goto("3.1 End-to-end testing")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_resume_on_running_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ═══════════════════════════════════════════════════════
# Generic / cross-cutting tests
# ═══════════════════════════════════════════════════════

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    h.submit({"model": "DDD aggregates"})

    h.save_checkpoint("at_domain_review")

    h.approve()
    h.submit_goto("2.0 Port loop")
    assert h.step == "2.1 Define port interface"

    restored = h.load_checkpoint("at_domain_review")
    assert restored is not None
    assert restored.current_step == "1.2 Domain review"
    assert "1.1 Design domain model" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    assert h.step == "1.1 Design domain model"

    r = h.retry()
    assert r
    assert h.step == "1.1 Design domain model"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step fails."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_back_returns_to_previous(harness_factory):
    """Back returns to the previously visited step."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Domain review"

    r = h.back()
    assert r
    assert h.step == "1.1 Design domain model"


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Design domain model"


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["a", "b", "c"]})
    _enter_port_loop(h)

    loop_info = h.state.loop_state["2.0 Port loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_port(h)
    h.submit_goto("2.0 Port loop")

    loop_info = h.state.loop_state["2.0 Port loop"]
    assert loop_info["i"] == 1


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["p1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Domain review"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "1.2 Domain review"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"


# ═══════════════════════════════════════════════════════
# Turing machine condition checker tests
# ═══════════════════════════════════════════════════════

def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["OrderRepositoryPort"]})
    h.start()
    h.register_node(
        "1.1 Design domain model",
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
    h = harness_factory("p3-hexagonal.yaml", loop_data={"ports": ["OrderRepositoryPort"]})
    h.start()
    h.register_node(
        "1.1 Design domain model",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
