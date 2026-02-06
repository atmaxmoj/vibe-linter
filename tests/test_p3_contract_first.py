"""Contract-First Development workflow tests."""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# ─── Helpers ───

def _walk_to_contract_review(h):
    """Start -> submit 1.1 -> arrive at 1.2 Contract review (waiting)."""
    h.start()
    h.submit({})
    assert h.step == "1.2 Contract review"
    assert h.status == "waiting"


def _enter_endpoint_loop(h):
    """Get past contract review and stubs into endpoint loop."""
    _walk_to_contract_review(h)
    h.approve()
    h.submit_goto("1.3 Generate stubs")
    h.submit({})
    assert h.step == "2.1 Implement endpoint"
    assert h.status == "running"


def _do_one_endpoint(h):
    """Complete one endpoint cycle: 2.1 -> 2.2."""
    h.submit({})   # 2.1 -> 2.2
    assert h.step == "2.2 Contract validation"


# ═══════════════════════════════════════════════════════
# Scenario 1-10: Existing tests (unchanged)
# ═══════════════════════════════════════════════════════

def test_complete_walkthrough(harness_factory):
    """Scenario 1: gRPC service for inter-service communication -- 4 RPCs defined in protobuf, all pass validation."""
    h = harness_factory(
        "p3-contract-first.yaml",
        loop_data={"endpoints": [
            "CreateOrder",
            "GetOrder",
            "ListOrdersByCustomer",
            "CancelOrder",
        ]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define contract"
    assert h.status == "running"

    # 1.1 Define the protobuf contract
    r = h.submit({
        "contract_type": "gRPC / Protocol Buffers",
        "proto_file": "order_service.proto",
        "package": "com.acme.orders.v1",
        "messages": {
            "Order": {"id": "string", "customer_id": "string", "items": "repeated OrderItem", "status": "OrderStatus", "created_at": "google.protobuf.Timestamp"},
            "OrderItem": {"product_id": "string", "quantity": "int32", "price_cents": "int64"},
            "OrderStatus": "enum(PENDING, CONFIRMED, SHIPPED, CANCELED)",
        },
        "rpcs": ["CreateOrder", "GetOrder", "ListOrdersByCustomer", "CancelOrder"],
    })
    assert r
    assert r.new_step == "1.2 Contract review"
    assert h.step == "1.2 Contract review"
    assert h.status == "waiting"

    # 1.2 Contract review approved
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("1.3 Generate stubs")
    assert r
    assert r.new_step == "1.3 Generate stubs"
    assert h.step == "1.3 Generate stubs"

    # 1.3 Generate server and client stubs from proto
    r = h.submit({
        "tool": "buf generate --template buf.gen.yaml",
        "generated": ["order_service_pb2.py", "order_service_pb2_grpc.py", "order_service_grpc.ts (client)"],
        "language": "Python (server) + TypeScript (client)",
    })
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # -- RPC 1: CreateOrder --
    r = h.submit({
        "rpc": "CreateOrder",
        "implementation": "Validates items, calculates total, inserts into orders table, publishes OrderCreated event to Kafka",
        "db": "INSERT INTO orders (id, customer_id, total_cents, status) VALUES ($1, $2, $3, 'PENDING')",
    })
    assert r
    assert r.new_step == "2.2 Contract validation"
    assert h.step == "2.2 Contract validation"

    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # -- RPC 2: GetOrder --
    r = h.submit({
        "rpc": "GetOrder",
        "implementation": "Fetches order by ID with LEFT JOIN on order_items, returns NOT_FOUND for missing orders",
    })
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # -- RPC 3: ListOrdersByCustomer --
    r = h.submit({
        "rpc": "ListOrdersByCustomer",
        "implementation": "Cursor-based pagination using (created_at, id) composite key, max page_size=100",
    })
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # -- RPC 4: CancelOrder --
    r = h.submit({
        "rpc": "CancelOrder",
        "implementation": "State machine transition: only PENDING/CONFIRMED can be canceled, publishes OrderCanceled event",
    })
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    assert h.step == "3.1 Bidirectional integration test"

    # Verify loop_state cleaned after loop exhaustion
    assert "2.0 Endpoint loop" not in (h.state.loop_state or {})

    # 3.1 Bidirectional: Python server + TypeScript client both pass
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_contract_validation_fails(harness_factory):
    """Scenario 2: UpdateInventory RPC fails validation 3 times -- field type mismatch, missing error codes, wrong enum."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["UpdateInventory"]})
    r = h.start()
    assert r

    r = h.submit({
        "contract_type": "gRPC / Protocol Buffers",
        "proto_file": "inventory_service.proto",
        "rpc": "UpdateInventory(UpdateInventoryRequest) returns (UpdateInventoryResponse)",
        "fields": {"sku": "string", "quantity_delta": "int32", "warehouse_id": "string"},
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.3 Generate stubs")
    assert r
    assert r.new_step == "1.3 Generate stubs"
    assert h.step == "1.3 Generate stubs"

    r = h.submit({"tool": "protoc --python_out=. --grpc_python_out=. inventory_service.proto"})
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # Verify loop first entry
    status = h.get_status()
    assert "[1/" in status["display_path"]

    # Fail 1: quantity_delta returned as string instead of int32
    r = h.submit({
        "rpc": "UpdateInventory",
        "issue": "Handler returns quantity_delta as JSON string '5' instead of protobuf int32",
    })
    assert r
    assert r.new_step == "2.2 Contract validation"
    assert h.step == "2.2 Contract validation"

    r = h.submit_goto("2.1 Implement endpoint")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # Fail 2: missing FAILED_PRECONDITION error code for negative stock
    r = h.submit({
        "rpc": "UpdateInventory",
        "fix": "Fixed int32 serialization",
        "issue": "Contract requires FAILED_PRECONDITION when stock goes negative, returning INTERNAL instead",
    })
    assert r
    assert r.new_step == "2.2 Contract validation"
    assert h.step == "2.2 Contract validation"

    r = h.submit_goto("2.1 Implement endpoint")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # Fail 3: InventoryStatus enum uses AVAILABLE but contract defines IN_STOCK
    r = h.submit({
        "rpc": "UpdateInventory",
        "fix": "Added FAILED_PRECONDITION for negative stock",
        "issue": "Response uses InventoryStatus.AVAILABLE but proto defines IN_STOCK",
    })
    assert r
    assert r.new_step == "2.2 Contract validation"
    assert h.step == "2.2 Contract validation"

    r = h.submit_goto("2.1 Implement endpoint")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # Attempt 4: all fixes applied, validation passes
    r = h.submit({
        "rpc": "UpdateInventory",
        "fix": "Aligned enum values to proto definition: AVAILABLE -> IN_STOCK",
        "all_checks_pass": True,
    })
    assert r
    assert r.new_step == "2.2 Contract validation"
    assert h.step == "2.2 Contract validation"

    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert h.step == "3.1 Bidirectional integration test"


def test_contract_rejected_redefine(harness_factory):
    """Scenario 3: Pact consumer contract rejected -- provider team requires backward-compatible field naming."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["GET /users/{id}/profile"]})
    r = h.start()
    assert r

    # First contract: uses snake_case field names
    r = h.submit({
        "contract_type": "Pact (consumer-driven)",
        "consumer": "mobile-app",
        "provider": "user-service",
        "interaction": "GET /users/{id}/profile returns {first_name, last_name, email_address}",
        "issue": "Provider already uses camelCase (firstName, lastName) in production",
    })
    assert r
    assert r.new_step == "1.2 Contract review"
    assert h.step == "1.2 Contract review"
    assert h.status == "waiting"

    # Provider team rejects: must use existing camelCase field names
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("1.1 Define contract")
    assert r
    assert r.new_step == "1.1 Define contract"
    assert h.step == "1.1 Define contract"
    assert h.status == "running"

    # Revised contract: aligned with provider's camelCase convention
    r = h.submit({
        "contract_type": "Pact (consumer-driven)",
        "consumer": "mobile-app",
        "provider": "user-service",
        "interaction": "GET /users/{id}/profile returns {firstName, lastName, emailAddress}",
        "note": "Aligned with provider's existing camelCase convention per API style guide",
    })
    assert r
    assert r.new_step == "1.2 Contract review"
    assert h.step == "1.2 Contract review"

    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("1.3 Generate stubs")
    assert r
    assert r.new_step == "1.3 Generate stubs"
    assert h.step == "1.3 Generate stubs"

    r = h.submit({"tool": "pact-stub-server --pact-file user-profile.pact.json --port 8080"})
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"


def test_bidirectional_fails_back_to_loop(harness_factory):
    """Scenario 4: Bidirectional test fails -- provider returns 200 but consumer expects 201 for CreateShipment."""
    h = harness_factory(
        "p3-contract-first.yaml",
        loop_data={"endpoints": ["CreateShipment", "TrackShipment"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "contract_type": "Pact",
        "consumer": "checkout-service",
        "provider": "shipping-service",
        "rpcs": ["CreateShipment (POST /shipments)", "TrackShipment (GET /shipments/{id}/tracking)"],
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.3 Generate stubs")
    assert r

    r = h.submit({"tool": "pact-stub-server", "stubs_generated": 2})
    assert r
    assert h.step == "2.1 Implement endpoint"

    # Implement both RPCs
    r = h.submit({"rpc": "CreateShipment", "handler": "POST /shipments", "returns": "201 with shipment_id"})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    r = h.submit({"rpc": "TrackShipment", "handler": "GET /shipments/{id}/tracking", "returns": "200 with tracking events"})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    assert h.step == "3.1 Bidirectional integration test"

    # Bidirectional fails: provider returns 200 for CreateShipment but consumer pact expects 201
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"
    assert h.status == "running"

    # Fix both endpoints
    r = h.submit({"rpc": "CreateShipment", "fix": "Changed response status from 200 to 201 Created per pact"})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    r = h.submit({"rpc": "TrackShipment", "fix": "Added empty tracking_events array for new shipments instead of 404"})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    assert h.step == "3.1 Bidirectional integration test"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_stop_then_resume(harness_factory):
    """Scenario 5: Stop during contract review -- waiting for external team to approve GraphQL schema federation."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["Query.product"]})
    r = h.start()
    assert r

    r = h.submit({
        "contract_type": "GraphQL Federation Schema",
        "subgraph": "product-subgraph",
        "schema": "type Product @key(fields: 'id') { id: ID!, name: String!, price: Money! }",
        "note": "Waiting for platform team to approve schema composition with gateway",
    })
    assert r
    assert r.new_step == "1.2 Contract review"
    assert h.step == "1.2 Contract review"

    # Stop: blocked on platform team's federation gateway compatibility check
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "1.2 Contract review"

    # Platform team approved federation composition -- resume
    r = h.resume()
    assert r
    assert h.status == "waiting"
    assert h.step == "1.2 Contract review"

    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("1.3 Generate stubs")
    assert r
    assert r.new_step == "1.3 Generate stubs"
    assert h.step == "1.3 Generate stubs"


def test_skip_stubs(harness_factory):
    """Scenario 6: Skip stub generation -- existing OpenAPI codegen output from a shared monorepo."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["POST /payments/refund"]})
    r = h.start()
    assert r

    r = h.submit({
        "contract_type": "OpenAPI 3.1 (shared monorepo)",
        "source": "packages/api-contracts/payment-service.yaml",
        "rpc": "POST /payments/refund",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.3 Generate stubs")
    assert r
    assert r.new_step == "1.3 Generate stubs"
    assert h.step == "1.3 Generate stubs"

    # Skip: stubs already generated by CI pipeline in the shared monorepo
    r = h.skip("Stubs auto-generated by monorepo CI -- packages/payment-client/src/generated/")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    r = h.submit({
        "rpc": "POST /payments/refund",
        "handler": "RefundController.create",
        "implementation": "Calls Stripe refund API, updates payment record status to REFUNDED",
    })
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_complete_then_reset(harness_factory):
    """Scenario 7: Ship Auth service contract v1, reset to start v2 with OIDC support."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["POST /auth/login"]})
    r = h.start()
    assert r

    r = h.submit({
        "contract_type": "OpenAPI 3.1",
        "service": "auth-service",
        "version": "1.0.0",
        "rpc": "POST /auth/login -- username/password login returning JWT",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.3 Generate stubs")
    assert r

    r = h.submit({"tool": "openapi-generator-cli generate -i auth.yaml -g python-flask"})
    assert r
    r = h.submit({
        "rpc": "POST /auth/login",
        "handler": "auth_controller.login",
        "implementation": "bcrypt password verify + JWT RS256 signing",
    })
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    r = h.submit_goto("Done")
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # v1 done -- cannot add OIDC support
    r = h.submit({})
    assert not r

    # Reset for v2: adding OIDC/SSO support
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define contract"
    assert h.status == "running"


def test_empty_endpoint_list(harness_factory):
    """Scenario 8: Contract review-only -- Thrift IDL review with no RPCs to implement yet."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": []})
    r = h.start()
    assert r

    r = h.submit({
        "contract_type": "Apache Thrift IDL",
        "service": "recommendation-service",
        "idl_file": "recommendation.thrift",
        "note": "Defining types and structs only -- RPCs will be added in next sprint",
        "structs": ["UserProfile", "ProductVector", "RecommendationScore"],
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.3 Generate stubs")
    assert r

    # Submit on 1.3 -> loop with empty list -> skips to 3.1
    r = h.submit({"tool": "thrift --gen py recommendation.thrift", "note": "Type stubs only, no service RPCs"})
    assert r

    assert h.step == "3.1 Bidirectional integration test"
    assert h.status == "running"


def test_back(harness_factory):
    """Scenario 9: Go back to revise AsyncAPI contract after realizing WebSocket events need different payload shape."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["ws.notification"]})
    r = h.start()
    assert r

    r = h.submit({
        "contract_type": "AsyncAPI 2.6",
        "channel": "ws://api.acme.com/notifications",
        "message": {"type": "NotificationEvent", "payload": {"title": "string", "body": "string"}},
    })
    assert r
    assert r.new_step == "1.2 Contract review"
    assert h.step == "1.2 Contract review"

    # Realized the payload needs a severity field -- go back
    r = h.back()
    assert r
    assert r.new_step == "1.1 Define contract"
    assert h.step == "1.1 Define contract"
    assert h.status == "running"

    r = h.submit({
        "contract_type": "AsyncAPI 2.6",
        "channel": "ws://api.acme.com/notifications",
        "message": {"type": "NotificationEvent", "payload": {"title": "string", "body": "string", "severity": "enum(info, warning, critical)"}},
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.3 Generate stubs")
    assert r

    r = h.submit({"tool": "asyncapi generate:fromTemplate asyncapi.yaml @asyncapi/python-paho-template"})
    assert r
    assert h.step == "2.1 Implement endpoint"

    # Realized stubs need regeneration with new template version -- go back
    r = h.back()
    assert r
    assert r.new_step == "1.3 Generate stubs"
    assert h.step == "1.3 Generate stubs"


def test_modify_yaml_add_versioning(harness_factory):
    """Scenario 10: Hot-reload YAML to add semantic versioning step after breaking change detected in proto."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["GetUser"]})
    r = h.start()
    assert r

    r = h.submit({
        "contract_type": "gRPC / Protocol Buffers",
        "proto_file": "user_service.proto",
        "package": "com.acme.users.v1",
        "note": "Breaking change detected: renamed 'username' to 'display_name' -- need versioning step",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.3 Generate stubs")
    assert r

    # Add versioning step via hot-reload
    yaml_content = """名称: Contract-First Development
描述: Formal contract, generate stubs, endpoint loop, bidirectional integration

步骤:
  - 1.1 Define contract

  - 1.2 Contract review:
      类型: wait
      下一步:
        - 如果: "contract is approved"
          去: 1.3 Version contract
        - 去: 1.1 Define contract

  - 1.3 Version contract:
      下一步: 1.4 Generate stubs

  - 1.4 Generate stubs

  - 2.0 Endpoint loop:
      遍历: "endpoints"
      子步骤:
        - 2.1 Implement endpoint
        - 2.2 Contract validation:
            下一步:
              - 如果: "endpoint conforms to contract"
                去: 2.0 Endpoint loop
              - 去: 2.1 Implement endpoint

  - 3.1 Bidirectional integration test:
      下一步:
        - 如果: "both provider and consumer pass"
          去: Done
        - 去: 2.0 Endpoint loop

  - Done:
      类型: terminate
      原因: Contract verified bidirectionally
"""
    h.reload_yaml(yaml_content)

    r = h.goto("1.3 Version contract")
    assert r
    assert r.new_step == "1.3 Version contract"
    assert h.step == "1.3 Version contract"
    assert h.status == "running"

    r = h.submit({
        "action": "Bumped package from com.acme.users.v1 to com.acme.users.v2",
        "breaking_changes": ["Renamed 'username' field to 'display_name'"],
        "buf_breaking": "buf breaking --against .git#branch=main --config buf.yaml",
    })
    assert r
    assert r.new_step == "1.4 Generate stubs"
    assert h.step == "1.4 Generate stubs"


# ═══════════════════════════════════════════════════════
# Dimension tests: Data accumulation
# ═══════════════════════════════════════════════════════

def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()

    h.submit({"contract": "REST v1"})
    data = h.state.data
    assert "1.1 Define contract" in data
    assert data["1.1 Define contract"]["contract"] == "REST v1"

    h.approve()
    h.submit_goto("1.3 Generate stubs")
    h.submit({"stubs": "generated"})
    data = h.state.data
    assert "1.3 Generate stubs" in data


def test_s2_data_after_validation_retry(harness_factory):
    """Data persists after validation retry loop."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    _enter_endpoint_loop(h)

    h.submit({"impl": "v1"})
    h.submit_goto("2.1 Implement endpoint")
    h.submit({"impl": "v2"})
    data = h.state.data
    assert data["2.1 Implement endpoint"]["impl"] == "v2"


# ═══════════════════════════════════════════════════════
# Dimension tests: History audit trail
# ═══════════════════════════════════════════════════════

def test_s1_history_audit_trail(harness_factory):
    """After walkthrough, history contains expected action sequence."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.submit({})
    h.approve()
    h.submit_goto("1.3 Generate stubs")
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Endpoint loop")
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "approve" in actions
    assert "submit" in actions
    assert "terminate" in actions[-1]


def test_s3_history_shows_reject_path(harness_factory):
    """History records the reject path through contract review."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.submit({})
    h.approve()
    h.submit_goto("1.1 Define contract")

    history = h.get_history(20)
    actions = [e["action"] for e in history]
    assert "approve" in actions
    assert "submit" in actions


# ═══════════════════════════════════════════════════════
# Dimension tests: Cross-executor recovery
# ═══════════════════════════════════════════════════════

def test_cross_executor_at_contract_review(harness_factory):
    """Close at contract review, reopen, state persists."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    _walk_to_contract_review(h)

    h.new_executor()

    assert h.step == "1.2 Contract review"
    assert h.status == "waiting"

    h.approve()
    r = h.submit_goto("1.3 Generate stubs")
    assert r
    assert h.step == "1.3 Generate stubs"


def test_cross_executor_mid_loop(harness_factory):
    """Close mid-loop, reopen, loop state preserved."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1", "e2"]})
    _enter_endpoint_loop(h)

    h.submit({"impl": "v1"})
    assert h.step == "2.2 Contract validation"

    h.new_executor()

    assert h.step == "2.2 Contract validation"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Endpoint loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.goto("3.1 Bidirectional integration test")
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

def test_node_validates_endpoint(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    _enter_endpoint_loop(h)

    h.register_node(
        "2.1 Implement endpoint",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("endpoint") else "must include endpoint",
        ),
    )

    r = h.submit({"notes": "no endpoint"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"endpoint": "POST /orders"})
    assert r
    assert r.new_step == "2.2 Contract validation"


def test_node_validates_contract(harness_factory):
    """Validate node on contract definition step."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()

    h.register_node(
        "1.1 Define contract",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("version") else "must include version",
        ),
    )

    r = h.submit({"description": "no version"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"version": "1.0"})
    assert r


# ═══════════════════════════════════════════════════════
# Dimension tests: Node archival
# ═══════════════════════════════════════════════════════

def test_node_archives_endpoints(harness_factory):
    """Archive node writes each endpoint to SQLite."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1", "e2"]})
    _enter_endpoint_loop(h)

    h.register_node(
        "2.1 Implement endpoint",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"name": "string", "status": "string"}},
            archive={"table": "contract_endpoints"},
        ),
    )

    for _i in range(2):
        h.submit({"name": f"ep_{_i}", "status": "implemented"})
        h.submit_goto("2.0 Endpoint loop")

    rows = h.get_archived_rows("contract_endpoints")
    assert len(rows) == 2
    assert rows[0]["name"] == "ep_0"
    assert rows[1]["name"] == "ep_1"


# ═══════════════════════════════════════════════════════
# Dimension tests: Error boundaries
# ═══════════════════════════════════════════════════════

def test_submit_on_waiting_fails(harness_factory):
    """Submit on a waiting step returns failure."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    _walk_to_contract_review(h)
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    assert h.status == "running"

    r = h.reject("bad")
    assert not r
    assert "not waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.goto("3.1 Bidirectional integration test")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.goto("3.1 Bidirectional integration test")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_resume_on_running_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ═══════════════════════════════════════════════════════
# Generic / cross-cutting tests
# ═══════════════════════════════════════════════════════

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.submit({"contract": "REST v1"})

    h.save_checkpoint("at_contract_review")

    h.approve()
    h.submit_goto("1.3 Generate stubs")
    assert h.step == "1.3 Generate stubs"

    restored = h.load_checkpoint("at_contract_review")
    assert restored is not None
    assert restored.current_step == "1.2 Contract review"
    assert "1.1 Define contract" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    assert h.step == "1.1 Define contract"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define contract"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step fails."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_back_returns_to_previous(harness_factory):
    """Back returns to the previously visited step."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Contract review"

    r = h.back()
    assert r
    assert h.step == "1.1 Define contract"


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define contract"


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["a", "b", "c"]})
    _enter_endpoint_loop(h)

    loop_info = h.state.loop_state["2.0 Endpoint loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_endpoint(h)
    h.submit_goto("2.0 Endpoint loop")

    loop_info = h.state.loop_state["2.0 Endpoint loop"]
    assert loop_info["i"] == 1


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Contract review"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "1.2 Contract review"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


# ═══════════════════════════════════════════════════════
# Turing machine condition checker tests
# ═══════════════════════════════════════════════════════

def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["CreateOrder"]})
    h.start()
    h.register_node(
        "1.1 Define contract",
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
    h = harness_factory("p3-contract-first.yaml", loop_data={"endpoints": ["CreateOrder"]})
    h.start()
    h.register_node(
        "1.1 Define contract",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
