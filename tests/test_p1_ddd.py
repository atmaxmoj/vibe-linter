"""Tests for DDD Development SOP (p1-ddd.yaml).

Workflow structure:
- 1.1 Identify bounded contexts
- 1.2 Define ubiquitous language
- 2.0 Context loop (iterate: "bounded_contexts")
  - 2.1 Design aggregates and entities
  - 2.2 Implement domain model
  - 2.3 Write domain tests
  - 2.4 Context review (wait, LLM: approved->2.0, minor fix->2.2, else->2.1)
- 3.1 Integrate bounded contexts
- 3.2 Integration testing
- 3.3 Final review (LLM: solid->Done, else->2.0)
- Done (terminate)

Dimensions tested per scenario:
  - State machine transitions (happy path)
  - Data accumulation (submit data persists in state.data)
  - History audit trail (action sequence in get_history)
  - Cross-executor recovery (close + new_executor + resume)
  - Node validation (validate node rejects bad data)
  - Node archival (archive node writes to SQLite)
  - Error boundaries (wrong-state operations fail gracefully)
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, EditPolicyPattern, NodeDefinition

# --- Helpers ---


def _walk_to_context_loop(h):
    """Common helper: start -> submit 1.1 -> submit 1.2 -> enter loop at 2.1."""
    h.start()
    h.submit({})   # 1.1 -> 1.2
    h.submit({})   # 1.2 -> 2.0 (loop header) -> 2.1
    assert h.step == "2.1 Design aggregates and entities"
    assert h.status == "running"


def _do_one_context_pass(h, data=None):
    """Complete one Design-Implement-Test cycle ending at context review."""
    h.submit(data or {})   # 2.1 -> 2.2
    h.submit(data or {})   # 2.2 -> 2.3
    h.submit(data or {})   # 2.3 -> 2.4
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"


def _approve_review_and_advance(h, target="2.0 Context loop"):
    """Approve wait step then submit_goto to advance past LLM step."""
    h.approve()
    assert h.status == "running"
    return h.submit_goto(target)


# ===============================================================
# Scenario 1: Three contexts complete (full walkthrough)
# ===============================================================

def test_three_contexts_complete(harness_factory):
    """E-commerce platform: Identity, Ordering, and Catalog bounded contexts, all approved first time."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["identity", "ordering", "catalog"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Identify bounded contexts"
    assert h.status == "running"

    # 1.1 Strategic design: identify the three core bounded contexts
    r = h.submit({
        "domain": "E-commerce Platform",
        "contexts": [
            {"name": "Identity", "responsibility": "User registration, authentication, roles, permissions"},
            {"name": "Ordering", "responsibility": "Cart, checkout, order lifecycle, payment orchestration"},
            {"name": "Catalog", "responsibility": "Products, categories, pricing, inventory read model"},
        ],
        "context_map": "Identity <-> Ordering (customer/conformist), Catalog <-> Ordering (shared kernel on ProductId)",
    })
    assert r
    assert r.new_step == "1.2 Define ubiquitous language"
    assert h.step == "1.2 Define ubiquitous language"
    assert h.status == "running"

    # 1.2 Define ubiquitous language across all contexts
    r = h.submit({
        "glossary": {
            "Customer": "A registered user who can place orders (Identity context owns, Ordering references)",
            "Order": "A confirmed purchase with line items, belongs to Ordering context",
            "Product": "A sellable item with SKU and price, owned by Catalog",
            "Cart": "Transient collection of product selections before checkout, Ordering context",
            "SKU": "Stock Keeping Unit, unique product identifier shared between Catalog and Ordering",
        },
        "anti_corruption_layers": [
            "Ordering sees Customer as CustomerId value object, never imports Identity's User aggregate",
            "Ordering references Product as OrderLineItem(sku, price_snapshot), decoupled from Catalog pricing",
        ],
    })
    assert r
    assert r.new_step == "2.1 Design aggregates and entities"
    assert h.step == "2.1 Design aggregates and entities"
    assert h.status == "running"

    # Verify loop state initialized
    status = h.get_status()
    assert "[1/" in status["display_path"]

    # ── Context 1: Identity ──
    # 2.1 Design aggregates for Identity context
    r = h.submit({
        "aggregate": "User",
        "entities": ["UserProfile", "Role"],
        "value_objects": ["Email", "HashedPassword", "UserId"],
        "domain_events": ["UserRegistered", "UserActivated", "RoleAssigned"],
        "invariants": ["Email must be unique across all users", "User must have at least one role"],
    })
    assert r
    assert r.new_step == "2.2 Implement domain model"

    # 2.2 Implement the Identity domain model
    r = h.submit({
        "files": ["src/identity/domain/user.py", "src/identity/domain/events.py"],
        "implementation": "User aggregate with register(), activate(), assign_role() methods, "
                          "raises domain events, Email value object with format validation",
        "patterns": "Factory method for User.register(), specification pattern for email uniqueness",
    })
    assert r
    assert r.new_step == "2.3 Write domain tests"

    # 2.3 Write domain tests for Identity
    r = h.submit({
        "test_file": "tests/identity/test_user_aggregate.py",
        "test_cases": [
            "test_register_user_raises_user_registered_event",
            "test_register_with_invalid_email_raises_value_error",
            "test_activate_already_active_user_is_idempotent",
            "test_assign_admin_role_requires_active_user",
        ],
        "passed": 4, "failed": 0,
    })
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    # 2.4 Context review: Identity approved
    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Context loop")
    assert r
    assert r.new_step == "2.1 Design aggregates and entities"
    assert h.step == "2.1 Design aggregates and entities"
    assert h.status == "running"

    # Verify second iteration
    status = h.get_status()
    assert "[2/" in status["display_path"]

    # ── Context 2: Ordering ──
    r = h.submit({
        "aggregate": "Order",
        "entities": ["OrderLineItem"],
        "value_objects": ["OrderId", "Money", "CustomerId", "OrderStatus"],
        "domain_events": ["OrderPlaced", "OrderPaid", "OrderShipped", "OrderCancelled"],
        "invariants": ["Order total must match sum of line items", "Cannot cancel a shipped order"],
    })
    assert r
    r = h.submit({
        "files": ["src/ordering/domain/order.py", "src/ordering/domain/events.py"],
        "implementation": "Order aggregate with place(), pay(), ship(), cancel() state machine, "
                          "Money value object with currency support",
    })
    assert r
    r = h.submit({
        "test_cases": [
            "test_place_order_calculates_total_from_line_items",
            "test_pay_order_transitions_to_paid_status",
            "test_cancel_shipped_order_raises_domain_error",
            "test_order_placed_event_contains_all_line_items",
        ],
        "passed": 4, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Context loop")
    assert r
    assert r.new_step == "2.1 Design aggregates and entities"
    assert h.step == "2.1 Design aggregates and entities"

    # Verify third iteration
    status = h.get_status()
    assert "[3/" in status["display_path"]

    # ── Context 3: Catalog ──
    r = h.submit({
        "aggregate": "Product",
        "entities": ["Category", "PriceEntry"],
        "value_objects": ["SKU", "ProductName", "Money"],
        "domain_events": ["ProductCreated", "PriceChanged", "ProductDiscontinued"],
        "invariants": ["SKU must be unique", "Price must be positive", "Discontinued product cannot be repriced"],
    })
    assert r
    r = h.submit({
        "implementation": "Product aggregate with create(), change_price(), discontinue(), "
                          "Category tree with parent references, PriceEntry with effective_from date",
    })
    assert r
    r = h.submit({
        "test_cases": [
            "test_create_product_with_initial_price",
            "test_change_price_raises_price_changed_event",
            "test_discontinue_product_blocks_further_price_changes",
        ],
        "passed": 3, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Context loop")
    assert r
    # Loop exhausted -> moves to after-loop step
    assert r.new_step == "3.1 Integrate bounded contexts"
    assert h.step == "3.1 Integrate bounded contexts"
    assert h.status == "running"

    # Verify loop state cleaned up
    assert "2.0 Context loop" not in h.state.loop_state

    # 3.1 Integrate bounded contexts via domain events and ACL
    r = h.submit({
        "integration_strategy": "Asynchronous domain events via RabbitMQ",
        "event_flows": [
            "UserRegistered (Identity) -> Ordering creates CustomerProfile",
            "OrderPlaced (Ordering) -> Catalog decrements inventory read model",
            "PriceChanged (Catalog) -> Ordering updates active cart line items",
        ],
        "anti_corruption_layers": ["OrderingCustomerACL", "OrderingProductACL"],
    })
    assert r
    assert r.new_step == "3.2 Integration testing"
    assert h.step == "3.2 Integration testing"

    # 3.2 Integration testing
    r = h.submit({
        "test_scenarios": [
            "User registers -> places order -> order total reflects current catalog prices",
            "Price changes while cart is open -> cart line items update on checkout",
            "Order placed -> inventory decremented in catalog read model",
        ],
        "passed": 12, "failed": 0,
    })
    assert r
    assert r.new_step == "3.3 Final review"
    assert h.step == "3.3 Final review"
    assert h.status == "running"

    # 3.3 Final review: integration is solid
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()

    h.submit({"contexts": "auth, billing"})
    data = h.state.data
    assert "1.1 Identify bounded contexts" in data
    assert data["1.1 Identify bounded contexts"]["contexts"] == "auth, billing"

    h.submit({"language": "user, account, session"})
    data = h.state.data
    assert "1.2 Define ubiquitous language" in data
    assert data["1.2 Define ubiquitous language"]["language"] == "user, account, session"

    h.submit({"aggregates": "UserAggregate"})
    data = h.state.data
    assert "2.1 Design aggregates and entities" in data
    assert data["2.1 Design aggregates and entities"]["aggregates"] == "UserAggregate"


def test_s1_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})
    h.submit({})
    # Loop iteration 1
    h.submit({})
    h.submit({})
    h.submit({})
    assert h.step == "2.4 Context review"
    h.approve()
    h.submit_goto("2.0 Context loop")
    # Loop exhausted
    assert h.step == "3.1 Integrate bounded contexts"
    h.submit({})
    h.submit({})
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "approve" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_s1_cross_executor_at_strategic_design(harness_factory):
    """Close executor at strategic design, reopen, continue."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({"contexts": "auth"})
    assert h.step == "1.2 Define ubiquitous language"

    h.new_executor()

    assert h.step == "1.2 Define ubiquitous language"
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert r.new_step == "2.1 Design aggregates and entities"


def test_s1_cross_executor_mid_loop(harness_factory):
    """Close executor mid-loop, reopen, loop state preserved."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth", "billing"]})
    _walk_to_context_loop(h)
    h.submit({"aggregates": "UserAggregate"})
    assert h.step == "2.2 Implement domain model"

    h.new_executor()

    assert h.step == "2.2 Implement domain model"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Context loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_s1_node_validates_aggregates(harness_factory):
    """Validate node rejects bad data, accepts good data on design step."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)

    h.register_node(
        "2.1 Design aggregates and entities",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("aggregates") else "must include aggregates",
        ),
    )

    r = h.submit({"notes": "vague design"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"aggregates": "UserAggregate"})
    assert r
    assert r.new_step == "2.2 Implement domain model"


def test_s1_node_archives_results(harness_factory):
    """Archive node writes submitted data to SQLite table."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)

    h.register_node(
        "2.1 Design aggregates and entities",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"aggregate": "string", "context": "string"}},
            archive={"table": "aggregate_designs"},
        ),
    )

    r = h.submit({"aggregate": "UserAggregate", "context": "auth"})
    assert r

    rows = h.get_archived_rows("aggregate_designs")
    assert len(rows) == 1
    assert rows[0]["aggregate"] == "UserAggregate"
    assert rows[0]["context"] == "auth"


def test_s1_error_submit_on_waiting(harness_factory):
    """Submit on waiting step (2.4 context review) returns failure."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


# ===============================================================
# Scenario 2: Context review rejected (redesign)
# ===============================================================

def test_context_review_rejected(harness_factory):
    """Booking system: Reservation context rejected for anemic domain model, redesigned with rich aggregates."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["reservation"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Identify bounded contexts"
    assert h.status == "running"

    # 1.1 Identify: hotel reservation system with single context for now
    r = h.submit({
        "domain": "Hotel Booking System",
        "contexts": [
            {"name": "Reservation", "responsibility": "Room availability, booking lifecycle, cancellation policy"},
        ],
    })
    assert r
    assert r.new_step == "1.2 Define ubiquitous language"

    # 1.2 Ubiquitous language
    r = h.submit({
        "glossary": {
            "Reservation": "A confirmed room booking for specific dates",
            "Room": "A bookable accommodation unit with type and rate",
            "Guest": "Person making the reservation",
            "Stay": "The period between check-in and check-out dates",
        },
    })
    assert r
    assert r.new_step == "2.1 Design aggregates and entities"

    # First attempt: anemic model with getters/setters
    r = h.submit({
        "aggregate": "Reservation",
        "design": "Reservation with status field, Room with availability boolean, "
                  "service layer does all business logic",
        "problem": "All behavior in ReservationService, domain objects are just data bags",
    })
    assert r
    assert r.new_step == "2.2 Implement domain model"

    r = h.submit({
        "implementation": "Reservation dataclass with status string, Room with is_available flag, "
                          "ReservationService.book() checks availability and sets status='confirmed'",
        "code_smell": "Transaction script pattern, not DDD",
    })
    assert r
    assert r.new_step == "2.3 Write domain tests"

    r = h.submit({
        "tests": ["test_book_room_sets_status_confirmed", "test_cancel_sets_status_cancelled"],
        "note": "Tests only check field values, no domain invariant enforcement",
    })
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    # Review rejects: anemic domain model, need rich aggregates
    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.step == "2.4 Context review"
    assert h.status == "running"

    # Go back to redesign aggregates with proper invariants
    r = h.submit_goto("2.1 Design aggregates and entities")
    assert r
    assert r.new_step == "2.1 Design aggregates and entities"
    assert h.step == "2.1 Design aggregates and entities"
    assert h.status == "running"

    # Second attempt: rich domain model
    r = h.submit({
        "aggregate": "Reservation",
        "entities": ["Stay"],
        "value_objects": ["DateRange", "RoomType", "GuestId", "Money"],
        "domain_events": ["ReservationConfirmed", "ReservationCancelled"],
        "invariants": [
            "Cannot book overlapping stays for the same room",
            "Cancellation within 24h of check-in incurs a penalty",
            "Stay dates must be in the future",
        ],
        "design": "Reservation aggregate encapsulates booking rules, Room aggregate manages availability calendar",
    })
    assert r
    r = h.submit({
        "implementation": "Reservation.confirm() enforces date validation and emits ReservationConfirmed, "
                          "Room.check_availability(date_range) uses calendar-based lookup, "
                          "CancellationPolicy value object calculates penalty",
    })
    assert r
    r = h.submit({
        "tests": [
            "test_confirm_reservation_with_past_dates_raises_domain_error",
            "test_cancel_within_24h_applies_penalty",
            "test_overlapping_reservation_raises_room_unavailable",
            "test_reservation_confirmed_event_emitted",
        ],
        "passed": 4, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    # Second review: approved
    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Context loop")
    assert r
    assert r.new_step == "3.1 Integrate bounded contexts"
    assert h.step == "3.1 Integrate bounded contexts"
    assert h.status == "running"


def test_s2_data_persists_through_redesign(harness_factory):
    """Data submitted during first attempt persists after redesign loop-back."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)

    h.submit({"aggregates": "v1 design"})
    h.submit({"model": "v1 model"})
    h.submit({})
    # At 2.4 waiting
    h.approve()
    h.submit_goto("2.1 Design aggregates and entities")

    h.submit({"aggregates": "v2 design"})
    data = h.state.data
    # Last submit for 2.1 wins
    assert data["2.1 Design aggregates and entities"]["aggregates"] == "v2 design"
    # But 2.2 data from first attempt is still there
    assert data["2.2 Implement domain model"]["model"] == "v1 model"


def test_s2_history_shows_redesign(harness_factory):
    """History contains approve + transition back to 2.1 after rejection loop."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)

    h.approve()
    h.submit_goto("2.1 Design aggregates and entities")

    history = h.get_history(30)
    actions = [e["action"] for e in history]
    assert "approve" in actions
    assert "transition" in actions


def test_s2_cross_executor_after_reject(harness_factory):
    """Close executor after redesign loop-back, reopen, state correct."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)
    h.approve()
    h.submit_goto("2.1 Design aggregates and entities")
    assert h.step == "2.1 Design aggregates and entities"

    h.new_executor()

    assert h.step == "2.1 Design aggregates and entities"
    assert h.status == "running"

    r = h.submit({"aggregates": "redesigned"})
    assert r
    assert r.new_step == "2.2 Implement domain model"


# ===============================================================
# Scenario 3: Repeated review (3 rounds with minor fixes)
# ===============================================================

def test_repeated_review_3_rounds(harness_factory):
    """Payment context: 3 rounds of minor fixes (missing idempotency, wrong event names, leaky abstraction)."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["payment"]})
    r = h.start()
    assert r

    # Strategic design
    r = h.submit({
        "domain": "Payment Processing",
        "contexts": [{"name": "Payment", "responsibility": "Payment intent lifecycle, refunds, provider abstraction"}],
    })
    assert r
    r = h.submit({
        "glossary": {
            "PaymentIntent": "A request to collect money, transitions through pending/captured/refunded",
            "Refund": "Partial or full reversal of a captured payment",
        },
    })
    assert r

    # Round 1: initial implementation missing idempotency
    r = h.submit({
        "aggregate": "PaymentIntent",
        "value_objects": ["Money", "PaymentMethodToken"],
        "domain_events": ["PaymentCaptured", "PaymentFailed"],
    })
    assert r
    r = h.submit({
        "implementation": "PaymentIntent.capture() calls provider, stores result",
        "issue": "No idempotency key, duplicate captures possible",
    })
    assert r
    r = h.submit({
        "tests": ["test_capture_payment", "test_capture_already_captured_raises"],
        "passed": 2, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    # Review: needs idempotency key
    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.2 Implement domain model")
    assert r
    assert r.new_step == "2.2 Implement domain model"
    assert h.step == "2.2 Implement domain model"
    assert h.status == "running"

    # Round 2: added idempotency but event names are wrong
    r = h.submit({
        "fix": "Added IdempotencyKey value object, PaymentIntent stores it on creation",
        "remaining_issue": "Events named PaymentCaptured/PaymentFailed leak Stripe terminology",
    })
    assert r
    assert r.new_step == "2.3 Write domain tests"

    r = h.submit({
        "tests": [
            "test_duplicate_capture_with_same_idempotency_key_is_noop",
            "test_different_idempotency_key_creates_new_intent",
        ],
        "passed": 4, "failed": 0,
    })
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    # Review: event names need to be provider-agnostic
    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.2 Implement domain model")
    assert r
    assert r.new_step == "2.2 Implement domain model"
    assert h.step == "2.2 Implement domain model"

    # Round 3: fixed event names but PaymentProvider interface leaks Stripe types
    r = h.submit({
        "fix": "Renamed events to PaymentCollected/PaymentDeclined, provider-agnostic",
        "remaining_issue": "PaymentProvider port still accepts stripe.PaymentMethod, leaky abstraction",
    })
    assert r
    r = h.submit({
        "tests": ["test_payment_collected_event_has_no_provider_specific_fields"],
        "passed": 5, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    # Review: still has leaky abstraction in port interface
    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.2 Implement domain model")
    assert r
    assert r.new_step == "2.2 Implement domain model"

    # Round 4: fixed port interface, finally approved
    r = h.submit({
        "fix": "PaymentProvider port now accepts domain's PaymentMethodToken VO, "
               "StripeAdapter converts to Stripe types in infrastructure layer",
    })
    assert r
    r = h.submit({
        "tests": ["test_provider_port_accepts_only_domain_types", "test_stripe_adapter_maps_to_stripe_types"],
        "passed": 7, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Context loop")
    assert r
    assert r.new_step == "3.1 Integrate bounded contexts"
    assert h.step == "3.1 Integrate bounded contexts"
    assert h.status == "running"


def test_s3_history_shows_repeated_reviews(harness_factory):
    """History reflects multiple approve + loop-back cycles."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)

    for _i in range(3):
        _do_one_context_pass(h)
        h.approve()
        h.submit_goto("2.2 Implement domain model")

    history = h.get_history(100)
    approve_entries = [e for e in history if e["action"] == "approve"]
    assert len(approve_entries) >= 3


def test_s3_cross_executor_mid_review(harness_factory):
    """Close executor at context review wait, reopen, still waiting."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.status == "running"


# ===============================================================
# Scenario 4: Loop wait stop resume
# ===============================================================

def test_loop_wait_stop_resume(harness_factory):
    """Logistics platform: Shipping context under review when sprint ends Friday, resume Monday."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["shipping", "warehouse"]})
    r = h.start()
    assert r

    # Strategic design for logistics platform
    r = h.submit({
        "domain": "Logistics Platform",
        "contexts": [
            {"name": "Shipping", "responsibility": "Shipment tracking, carrier selection, delivery estimation"},
            {"name": "Warehouse", "responsibility": "Inventory storage, picking, packing, stock levels"},
        ],
    })
    assert r
    r = h.submit({
        "glossary": {
            "Shipment": "A package in transit from warehouse to destination",
            "Carrier": "A shipping provider (FedEx, UPS, DHL)",
            "PickList": "Ordered list of items to retrieve from warehouse shelves",
        },
    })
    assert r

    # Complete Shipping context
    r = h.submit({
        "aggregate": "Shipment",
        "value_objects": ["TrackingNumber", "Address", "CarrierId", "Weight"],
        "domain_events": ["ShipmentDispatched", "ShipmentDelivered", "ShipmentDelayed"],
    })
    assert r
    r = h.submit({
        "implementation": "Shipment aggregate with dispatch(), update_tracking(), mark_delivered(), "
                          "CarrierSelectionPolicy chooses cheapest carrier within SLA",
    })
    assert r
    r = h.submit({
        "tests": [
            "test_dispatch_assigns_tracking_number",
            "test_carrier_selection_respects_weight_limits",
            "test_mark_delivered_emits_event",
        ],
        "passed": 3, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    # Friday 5pm: sprint ends, domain expert unavailable for review until Monday
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.4 Context review"

    # Cannot approve while stopped
    result = h.executor.approve({})
    assert not result

    # Monday 9am: domain expert is back, resume
    r = h.resume()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.status == "waiting"
    assert h.step == "2.4 Context review"

    # Domain expert approves Shipping context
    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.step == "2.4 Context review"
    assert h.status == "running"

    # Move to next context: Warehouse
    r = h.submit_goto("2.0 Context loop")
    assert r
    assert r.new_step == "2.1 Design aggregates and entities"
    assert h.step == "2.1 Design aggregates and entities"
    assert h.status == "running"


def test_s4_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": []})
    h.start()
    h.submit({})
    h.submit({})
    # Empty loop -> skip to 3.1
    h.submit({})
    h.submit({})
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_s4_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_s4_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


def test_s4_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})
    h.submit({})
    # Now in the loop at 2.1
    h.submit({})
    assert h.step == "2.2 Implement domain model"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()
    assert h.step == "2.2 Implement domain model"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert r.new_step == "2.3 Write domain tests"


# ===============================================================
# Scenario 5: Empty context list
# ===============================================================

def test_empty_context_list(harness_factory):
    """Greenfield project: strategic design only, no contexts identified yet, skip straight to integration planning."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": []})
    r = h.start()
    assert r
    assert h.step == "1.1 Identify bounded contexts"

    # 1.1 Event storming session reveals no clear boundaries yet
    r = h.submit({
        "domain": "Internal Knowledge Base",
        "event_storming_result": "All domain events cluster around a single 'Document' concept, "
                                 "no clear bounded context boundaries emerged",
        "decision": "Start with a single module, extract contexts when complexity demands it",
    })
    assert r
    assert r.new_step == "1.2 Define ubiquitous language"

    # 1.2 Define language even without separate contexts
    r = h.submit({
        "glossary": {
            "Document": "A knowledge article with title, body, and metadata",
            "Tag": "A label for categorizing documents",
            "Author": "Person who created or last edited a document",
        },
        "note": "Single bounded context for now, will split when search or collaboration gets complex",
    })
    assert r
    # Empty loop should skip to integration
    assert r.new_step == "3.1 Integrate bounded contexts"
    assert h.step == "3.1 Integrate bounded contexts"
    assert h.status == "running"

    # 3.1 No contexts to integrate, just set up the monolith structure
    r = h.submit({
        "structure": "Single Django app with domain/ and infrastructure/ packages",
        "note": "No inter-context integration needed yet",
    })
    assert r
    assert r.new_step == "3.2 Integration testing"

    # 3.2 Basic smoke tests
    r = h.submit({
        "tests": ["test_create_document", "test_search_by_tag", "test_author_attribution"],
        "passed": 3, "failed": 0,
    })
    assert r
    assert r.new_step == "3.3 Final review"

    # 3.3 Approved for initial release
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_s5_data_with_empty_loop(harness_factory):
    """Data is accumulated even when loop is skipped."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": []})
    h.start()
    h.submit({"contexts": "none yet"})
    h.submit({"language": "TBD"})
    # Loop skipped, at 3.1
    assert h.step == "3.1 Integrate bounded contexts"

    data = h.state.data
    assert data["1.1 Identify bounded contexts"]["contexts"] == "none yet"
    assert data["1.2 Define ubiquitous language"]["language"] == "TBD"


# ===============================================================
# Scenario 6: Skip context
# ===============================================================

def test_skip_context(harness_factory):
    """Notification context: skip domain expert review, team is confident in the model."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["notification"]})
    r = h.start()
    assert r

    # Quick strategic design for notification context
    r = h.submit({
        "domain": "Notification Service",
        "contexts": [{"name": "Notification", "responsibility": "Email, SMS, push notification delivery and preferences"}],
    })
    assert r
    r = h.submit({
        "glossary": {
            "Notification": "A message to be delivered through one or more channels",
            "Channel": "Delivery mechanism: email, SMS, or push",
            "Preference": "User's opt-in/opt-out settings per channel",
        },
    })
    assert r

    # Implement the notification context
    r = h.submit({
        "aggregate": "Notification",
        "value_objects": ["NotificationId", "Channel", "Recipient", "MessageContent"],
        "domain_events": ["NotificationSent", "NotificationFailed", "NotificationBounced"],
    })
    assert r
    r = h.submit({
        "implementation": "Notification.send() dispatches to channel adapter, "
                          "respects Preference aggregate for opt-outs, retries on transient failures",
    })
    assert r
    r = h.submit({
        "tests": ["test_send_respects_opt_out", "test_retry_on_transient_failure", "test_bounce_updates_preference"],
        "passed": 3, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    # Team is confident, domain expert is on vacation, skip the review
    r = h.goto("3.1 Integrate bounded contexts")
    assert r
    assert r.new_step == "3.1 Integrate bounded contexts"
    assert h.step == "3.1 Integrate bounded contexts"
    assert h.status == "running"


def test_s6_skip_records_reason(harness_factory):
    """Skip reason appears in history data field."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()

    h.skip("skip strategic design")
    history = h.get_history(5)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "skip strategic design"


# ===============================================================
# Scenario 7: Integration problem back to loop
# ===============================================================

def test_integration_problem_back_loop(harness_factory):
    """Insurance claims: Claim context passes review but integration reveals aggregate boundary is wrong."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["claims"]})
    r = h.start()
    assert r

    # Strategic design
    r = h.submit({
        "domain": "Insurance Claims Processing",
        "contexts": [{"name": "Claims", "responsibility": "Claim submission, assessment, approval, payout"}],
    })
    assert r
    r = h.submit({
        "glossary": {
            "Claim": "A request for insurance payout after an incident",
            "Assessment": "Evaluation of a claim by an adjuster",
            "Payout": "Money transferred to the claimant",
        },
    })
    assert r

    # First implementation: Claim aggregate holds everything
    r = h.submit({
        "aggregate": "Claim",
        "entities": ["Assessment", "Payout"],
        "domain_events": ["ClaimSubmitted", "ClaimAssessed", "PayoutApproved"],
        "design": "Single Claim aggregate containing Assessment and Payout as nested entities",
    })
    assert r
    r = h.submit({
        "implementation": "Claim aggregate with submit(), assess(), approve_payout() methods, "
                          "Assessment and Payout are entities within the Claim aggregate boundary",
    })
    assert r
    r = h.submit({
        "tests": ["test_submit_claim", "test_assess_claim", "test_approve_payout_after_assessment"],
        "passed": 3, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    # Context review passes (domain model looks correct in isolation)
    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Context loop")
    assert r
    assert r.new_step == "3.1 Integrate bounded contexts"
    assert h.step == "3.1 Integrate bounded contexts"
    assert h.status == "running"

    # 3.1 Integration: try to connect with Policy context
    r = h.submit({
        "integration": "Claims context subscribes to PolicyIssued events from Policy context",
        "problem": "Claim aggregate is too large: concurrent assessors cause optimistic lock conflicts, "
                   "Payout should be a separate aggregate to allow parallel processing",
    })
    assert r
    assert r.new_step == "3.2 Integration testing"

    # 3.2 Integration tests reveal the concurrency problem
    r = h.submit({
        "tests": [
            "test_concurrent_assessors_on_same_claim_fails_with_lock_conflict",
            "test_payout_blocked_until_assessment_complete",
        ],
        "passed": 1, "failed": 1,
        "failure_reason": "OptimisticLockError when two adjusters assess simultaneously",
    })
    assert r
    assert r.new_step == "3.3 Final review"
    assert h.step == "3.3 Final review"

    # 3.3 Final review: integration fails, need to split the aggregate
    r = h.submit_goto("2.0 Context loop")
    assert r
    assert r.new_step == "2.1 Design aggregates and entities"
    assert h.step == "2.1 Design aggregates and entities"
    assert h.status == "running"

    # Redesign: split Claim and Payout into separate aggregates
    r = h.submit({
        "aggregates": ["Claim", "Payout"],
        "design": "Claim aggregate owns submission and assessment, Payout is a separate aggregate "
                  "linked by ClaimId, allowing independent lifecycle and no lock contention",
        "domain_events": ["ClaimAssessed -> triggers PayoutCreation saga"],
    })
    assert r
    r = h.submit({
        "implementation": "Claim.assess() emits ClaimAssessed, PayoutSaga listens and creates Payout aggregate, "
                          "Payout.approve() and Payout.execute() are independent of Claim locks",
    })
    assert r
    r = h.submit({
        "tests": [
            "test_concurrent_assessors_no_longer_conflict",
            "test_payout_created_after_claim_assessed_event",
            "test_payout_lifecycle_independent_of_claim",
        ],
        "passed": 3, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    # Second review: split aggregate approved
    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Context loop")
    assert r
    assert r.new_step == "3.1 Integrate bounded contexts"
    assert h.step == "3.1 Integrate bounded contexts"
    assert h.status == "running"

    # 3.1 Re-integrate with proper aggregate boundaries
    r = h.submit({
        "integration": "Claims -> Payout via domain events, no direct aggregate references",
        "result": "Concurrent assessors work, payouts process independently",
    })
    assert r
    r = h.submit({
        "tests": ["test_end_to_end_claim_to_payout", "test_concurrent_assessment_and_payout"],
        "passed": 8, "failed": 0,
    })
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_s7_data_after_integration_rework(harness_factory):
    """Data from reworked contexts overwrites previous."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)
    _approve_review_and_advance(h)
    # Now at 3.1
    h.submit({"integration": "v1"})
    h.submit({})
    # At 3.3, go back to loop
    h.submit_goto("2.0 Context loop")
    h.submit({"aggregates": "reworked design"})

    data = h.state.data
    assert data["2.1 Design aggregates and entities"]["aggregates"] == "reworked design"
    assert data["3.1 Integrate bounded contexts"]["integration"] == "v1"


def test_s7_cross_executor_at_final_review(harness_factory):
    """Close executor at final review, reopen, state persists."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)
    _approve_review_and_advance(h)
    h.submit({})
    h.submit({})
    assert h.step == "3.3 Final review"

    h.new_executor()

    assert h.step == "3.3 Final review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


# ===============================================================
# Scenario 8: Done and reset
# ===============================================================

def test_done_reset(harness_factory):
    """CRM v1 shipped with Contact context, reset to start v2 with Sales Pipeline context."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["contact"]})
    r = h.start()
    assert r

    # V1: Contact management context
    r = h.submit({
        "domain": "CRM System v1",
        "contexts": [{"name": "Contact", "responsibility": "Contact records, company associations, interaction history"}],
    })
    assert r
    r = h.submit({
        "glossary": {
            "Contact": "A person the sales team interacts with",
            "Company": "An organization a contact belongs to",
            "Interaction": "A logged touchpoint (call, email, meeting)",
        },
    })
    assert r

    # Implement Contact context
    r = h.submit({
        "aggregate": "Contact",
        "value_objects": ["ContactId", "Email", "PhoneNumber"],
        "domain_events": ["ContactCreated", "InteractionLogged"],
    })
    assert r
    r = h.submit({
        "implementation": "Contact aggregate with log_interaction(), associate_company(), "
                          "Company is a separate aggregate referenced by CompanyId",
    })
    assert r
    r = h.submit({
        "tests": ["test_create_contact", "test_log_interaction", "test_associate_company"],
        "passed": 3, "failed": 0,
    })
    assert r
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert r.new_step == "2.4 Context review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Context loop")
    assert r
    assert r.new_step == "3.1 Integrate bounded contexts"

    # Integration and final review
    r = h.submit({
        "integration": "Single context, no inter-context integration needed for v1",
    })
    assert r
    r = h.submit({
        "tests": ["test_contact_crud_e2e", "test_interaction_timeline"],
        "passed": 5, "failed": 0,
    })
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"

    # V1 shipped, reset for V2 with Sales Pipeline context
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Identify bounded contexts"
    assert h.status == "running"


def test_s8_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_s8_reset_clears_data(harness_factory):
    """After reset, state is None."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({"contexts": "auth"})
    h.submit({"language": "user, account"})

    h.reset()
    assert h.state is None


def test_s8_fresh_start_after_reset(harness_factory):
    """Reset then start gives a clean initial state."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})

    h.reset()
    h.start()

    assert h.step == "1.1 Identify bounded contexts"
    assert h.status == "running"
    data = h.state.data
    assert "2.1 Design aggregates and entities" not in data


# ===============================================================
# Scenario 9: Modify YAML add context
# ===============================================================

def test_modify_yaml_add_context(harness_factory):
    """Healthcare system: mid-sprint, compliance team mandates aggregate invariant validation step."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["patient"]})
    r = h.start()
    assert r

    # Strategic design for healthcare system
    r = h.submit({
        "domain": "Healthcare Records System",
        "contexts": [{"name": "Patient", "responsibility": "Patient demographics, medical history, consent management"}],
    })
    assert r
    assert r.new_step == "1.2 Define ubiquitous language"

    r = h.submit({
        "glossary": {
            "Patient": "An individual receiving medical care",
            "MedicalRecord": "Chronological log of diagnoses, treatments, and observations",
            "Consent": "Patient's authorization for data sharing or procedures",
        },
    })
    assert r
    assert r.new_step == "2.1 Design aggregates and entities"
    assert h.step == "2.1 Design aggregates and entities"

    # Compliance team requires mandatory invariant validation before implementation
    new_yaml = """name: DDD Development
description: Modified with validation step

steps:
  - 1.1 Identify bounded contexts

  - 1.2 Define ubiquitous language

  - 2.0 Context loop:
      iterate: "bounded_contexts"
      children:
        - 2.1 Design aggregates and entities
        - 2.15 Validate aggregate design
        - 2.2 Implement domain model
        - 2.3 Write domain tests
        - 2.4 Context review:
            type: wait
            next:
              - if: "context implementation is approved"
                go: 2.0 Context loop
              - if: "needs minor fixes"
                go: 2.2 Implement domain model
              - go: 2.1 Design aggregates and entities

  - 3.1 Integrate bounded contexts

  - 3.2 Integration testing

  - 3.3 Final review:
      next:
        - if: "integration is solid"
          go: Done
        - go: 2.0 Context loop

  - Done:
      type: terminate
      reason: All bounded contexts integrated
"""
    h.reload_yaml(new_yaml)

    # Jump to the new compliance validation step
    r = h.goto("2.15 Validate aggregate design")
    assert r
    assert r.new_step == "2.15 Validate aggregate design"
    assert h.step == "2.15 Validate aggregate design"
    assert h.status == "running"

    # Validate: HIPAA compliance check on Patient aggregate design
    r = h.submit({
        "validation": "Patient aggregate enforces consent-before-access invariant, "
                      "MedicalRecord encrypted at rest, audit trail on all mutations",
        "hipaa_checklist": ["PHI access logging", "consent verification", "data encryption", "breach notification"],
        "result": "All 4 HIPAA requirements addressed in aggregate design",
    })
    assert r
    assert r.new_step == "2.2 Implement domain model"
    assert h.step == "2.2 Implement domain model"
    assert h.status == "running"


def test_s9_cross_executor_after_reload(harness_factory):
    """After YAML reload, close executor, reopen, state persists."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "2.1 Design aggregates and entities"

    h.new_executor()
    assert h.step == "2.1 Design aggregates and entities"
    assert h.status == "running"


def test_s9_node_on_new_step(harness_factory):
    """Install validate node for a step added by YAML reload."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "2.1 Design aggregates and entities"

    new_yaml = """name: DDD Development
description: Modified with validation step

steps:
  - 1.1 Identify bounded contexts

  - 1.2 Define ubiquitous language

  - 2.0 Context loop:
      iterate: "bounded_contexts"
      children:
        - 2.1 Design aggregates and entities
        - 2.15 Validate aggregate design
        - 2.2 Implement domain model
        - 2.3 Write domain tests
        - 2.4 Context review:
            type: wait
            next:
              - if: "context implementation is approved"
                go: 2.0 Context loop
              - if: "needs minor fixes"
                go: 2.2 Implement domain model
              - go: 2.1 Design aggregates and entities

  - 3.1 Integrate bounded contexts

  - 3.2 Integration testing

  - 3.3 Final review:
      next:
        - if: "integration is solid"
          go: Done
        - go: 2.0 Context loop

  - Done:
      type: terminate
      reason: All bounded contexts integrated
"""
    h.reload_yaml(new_yaml)

    h.submit({})
    assert h.step == "2.15 Validate aggregate design"

    h.register_node(
        "2.15 Validate aggregate design",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("validated") else "must validate design",
        ),
    )

    r = h.submit({"notes": "not validated"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"validated": True})
    assert r
    assert r.new_step == "2.2 Implement domain model"


# ===============================================================
# Scenario 10: Goto integration
# ===============================================================

def test_goto_integration(harness_factory):
    """Existing microservices migration: contexts already built, jump straight to integration."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Identify bounded contexts"
    assert h.status == "running"

    # Team already has 3 microservices built over the past year, just need to integrate them
    # using proper DDD patterns (anti-corruption layers, domain events)
    r = h.goto("3.1 Integrate bounded contexts")
    assert r
    assert r.new_step == "3.1 Integrate bounded contexts"
    assert h.step == "3.1 Integrate bounded contexts"
    assert h.status == "running"

    # 3.1 Define integration strategy between existing services
    r = h.submit({
        "existing_services": ["user-service (Go)", "order-service (Python)", "inventory-service (Java)"],
        "integration_strategy": "Replace REST-based synchronous calls with domain event bus (Kafka), "
                                "add anti-corruption layers at each service boundary",
        "event_contracts": [
            "UserCreated(user_id, email) -> order-service creates CustomerProfile",
            "OrderPlaced(order_id, items[]) -> inventory-service reserves stock",
            "StockDepleted(sku) -> order-service marks product unavailable",
        ],
    })
    assert r
    assert r.new_step == "3.2 Integration testing"
    assert h.step == "3.2 Integration testing"
    assert h.status == "running"

    # 3.2 Integration tests with Kafka testcontainers
    r = h.submit({
        "test_framework": "Testcontainers with Kafka + all 3 services",
        "scenarios_tested": [
            "User signup triggers customer profile creation in order-service",
            "Order placement reserves inventory, stock depletion propagates back",
            "Event ordering guaranteed per aggregate via partition key",
        ],
        "passed": 9, "failed": 0,
        "latency": "Event propagation < 200ms p99 in test environment",
    })
    assert r
    assert r.new_step == "3.3 Final review"
    assert h.step == "3.3 Final review"
    assert h.status == "running"

    # 3.3 Final review: integration is solid, ship it
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_s10_goto_does_not_add_data(harness_factory):
    """Goto does not produce a data entry."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.goto("3.1 Integrate bounded contexts")

    data = h.state.data
    assert "3.1 Integrate bounded contexts" not in data

    h.submit({"integration": "done"})
    data = h.state.data
    assert "3.1 Integrate bounded contexts" in data


def test_s10_history_shows_goto(harness_factory):
    """History records a goto action."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.goto("3.1 Integrate bounded contexts")

    history = h.get_history(10)
    actions = [e["action"] for e in history]
    assert "goto" in actions


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({"contexts": "auth"})
    h.submit({"language": "user, account"})

    h.save_checkpoint("at_loop_start")

    h.submit({})
    h.submit({})
    h.submit({})
    assert h.step == "2.4 Context review"

    restored = h.load_checkpoint("at_loop_start")
    assert restored is not None
    assert restored.current_step == "2.1 Design aggregates and entities"
    assert "1.2 Define ubiquitous language" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Define ubiquitous language"

    r = h.retry()
    assert r
    assert h.step == "1.2 Define ubiquitous language"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_back_returns_to_previous(harness_factory):
    """Back returns to the previously visited step."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Define ubiquitous language"

    h.submit({})
    assert h.step == "2.1 Design aggregates and entities"

    r = h.back()
    assert r
    assert h.step == "1.2 Define ubiquitous language"


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": []})
    h.start()
    h.submit({})
    h.submit({})
    # Empty loop -> skip to 3.1
    h.submit({})
    h.submit({})
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})

    for _i in range(3):
        h.start()
        h.submit({})
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Identify bounded contexts"


def test_history_records_transition_steps(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.0 -> 2.1

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_reject_on_non_waiting_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_preserves_data(harness_factory):
    """Reject does not modify state.data."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)

    data_before = dict(h.state.data)
    h.reject("bad review")
    data_after = h.state.data
    assert data_before == data_after


def test_reject_adds_history(harness_factory):
    """Reject action appears in history."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)

    h.reject("bad implementation")
    history = h.get_history(10)
    reject_entries = [e for e in history if e["action"] == "reject"]
    assert len(reject_entries) >= 1
    assert reject_entries[0]["data"] == "bad implementation"


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["a", "b", "c"]})
    _walk_to_context_loop(h)

    loop_info = h.state.loop_state["2.0 Context loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_context_pass(h)
    _approve_review_and_advance(h)

    loop_info = h.state.loop_state["2.0 Context loop"]
    assert loop_info["i"] == 1

    _do_one_context_pass(h)
    _approve_review_and_advance(h)

    loop_info = h.state.loop_state["2.0 Context loop"]
    assert loop_info["i"] == 2


def test_loop_cleanup_on_exit(harness_factory):
    """Loop state is cleaned up after all iterations complete."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["only"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)
    _approve_review_and_advance(h)

    assert h.step == "3.1 Integrate bounded contexts"
    assert "2.0 Context loop" not in h.state.loop_state


def test_node_archives_per_iteration(harness_factory):
    """Archive node accumulates one row per loop iteration."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["a", "b"]})
    _walk_to_context_loop(h)

    h.register_node(
        "2.1 Design aggregates and entities",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"aggregate": "string"}},
            archive={"table": "context_designs"},
        ),
    )

    # Iteration 1
    h.submit({"aggregate": "UserAggregate"})
    h.submit({})
    h.submit({})
    h.approve()
    h.submit_goto("2.0 Context loop")

    # Iteration 2
    h.submit({"aggregate": "OrderAggregate"})
    h.submit({})
    h.submit({})
    h.approve()
    h.submit_goto("2.0 Context loop")

    rows = h.get_archived_rows("context_designs")
    assert len(rows) == 2
    assert rows[0]["aggregate"] == "UserAggregate"
    assert rows[1]["aggregate"] == "OrderAggregate"


def test_cross_executor_preserves_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state intact."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["a", "b", "c"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)
    _approve_review_and_advance(h)

    # Mid iteration 2
    h.submit({"aggregates": "mid_loop"})
    assert h.step == "2.2 Implement domain model"

    h.new_executor()

    assert h.step == "2.2 Implement domain model"
    loop_info = h.state.loop_state["2.0 Context loop"]
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": []})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_edit_policy_reported_in_status(harness_factory):
    """get_status() includes edit_policy from registered node."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)

    h.register_node(
        "2.1 Design aggregates and entities",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="warn",
                patterns=[
                    EditPolicyPattern(glob="src/domain/**", policy="silent"),
                    EditPolicyPattern(glob="src/infra/**", policy="block"),
                ],
            ),
        ),
    )

    status = h.get_status()
    assert status["current_step"] == "2.1 Design aggregates and entities"
    assert status["node"] is not None
    assert status["node"]["edit_policy"]["default"] == "warn"


def test_resume_wait_step_restores_waiting(harness_factory):
    """Resuming on a wait step restores waiting status."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    _walk_to_context_loop(h)
    _do_one_context_pass(h)
    assert h.step == "2.4 Context review"
    assert h.status == "waiting"

    h.stop()
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"
    assert h.step == "2.4 Context review"


def test_cross_executor_preserves_data(harness_factory):
    """Close executor mid-flow, reopen, data persists."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({"contexts": "auth, billing"})
    h.submit({"language": "user, account"})

    h.new_executor()

    assert h.step == "2.1 Design aggregates and entities"
    data = h.state.data
    assert data["1.1 Identify bounded contexts"]["contexts"] == "auth, billing"
    assert data["1.2 Define ubiquitous language"]["language"] == "user, account"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "2.1 Design aggregates and entities"

    h.register_node(
        "2.1 Design aggregates and entities",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step by following DDD principles.\n\n## Steps\n1. Analyze requirements\n2. Design aggregates\n3. Submit output",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory("p1-ddd.yaml", loop_data={"bounded_contexts": ["auth"]})
    h.start()
    assert h.step == "1.1 Identify bounded contexts"

    h.register_node(
        "1.1 Identify bounded contexts",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="block",
                patterns=[],
            ),
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["edit_policy"] is not None
    assert status["node"]["edit_policy"]["default"] == "block"
