"""API-First Development workflow tests."""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# ─── Helpers ───

def _walk_to_spec_review(h):
    """Start -> submit 1.1 -> arrive at 1.2 Spec review (waiting)."""
    h.start()
    h.submit({})
    assert h.step == "1.2 Spec review"
    assert h.status == "waiting"


def _enter_endpoint_loop(h):
    """Get past spec review into first iteration of endpoint loop."""
    _walk_to_spec_review(h)
    h.approve()
    h.submit_goto("2.0 Endpoint loop")
    assert h.step == "2.1 Implement endpoint"
    assert h.status == "running"


def _do_one_endpoint(h):
    """Complete one endpoint cycle: 2.1 -> 2.2 -> 2.3."""
    h.submit({})   # 2.1 -> 2.2
    h.submit({})   # 2.2 -> 2.3
    assert h.step == "2.3 Contract test"


def _complete_flow(h, n_endpoints):
    """From endpoint loop entry, complete all iterations and finish."""
    for _i in range(n_endpoints):
        if h.step != "2.1 Implement endpoint":
            h.submit_goto("2.0 Endpoint loop")
        _do_one_endpoint(h)
        h.submit_goto("2.0 Endpoint loop")
    assert h.step == "3.1 Integration testing"
    h.submit_goto("3.2 Generate documentation")
    h.submit({})
    assert h.step == "Done"
    assert h.status == "done"


# ═══════════════════════════════════════════════════════
# Scenario 1: Full walkthrough (existing)
# ═══════════════════════════════════════════════════════

def test_five_endpoints_complete(harness_factory):
    """Scenario 1: Build a multi-tenant SaaS billing API with 5 RESTful endpoints."""
    h = harness_factory(
        "p3-api-first.yaml",
        loop_data={"endpoints": [
            "POST /tenants/{id}/subscriptions",
            "GET /tenants/{id}/invoices",
            "POST /invoices/{id}/payments",
            "GET /usage/metrics",
            "POST /webhooks/stripe",
        ]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Write OpenAPI spec"
    assert h.status == "running"

    # 1.1 Write the OpenAPI 3.1 spec for the billing API
    r = h.submit({
        "spec_version": "3.1.0",
        "title": "Multi-Tenant Billing API",
        "base_path": "/api/v1",
        "auth": "Bearer JWT with tenant_id claim",
        "schemas": {
            "Subscription": {"tenant_id": "uuid", "plan": "enum(free,pro,enterprise)", "status": "enum(active,canceled,past_due)"},
            "Invoice": {"id": "uuid", "amount_cents": "integer", "currency": "string", "due_date": "date"},
            "Payment": {"invoice_id": "uuid", "stripe_payment_intent_id": "string", "status": "enum(pending,succeeded,failed)"},
            "UsageMetric": {"tenant_id": "uuid", "metric_name": "string", "value": "number", "timestamp": "datetime"},
        },
        "endpoints_count": 5,
    })
    assert r
    assert r.new_step == "1.2 Spec review"
    assert h.step == "1.2 Spec review"
    assert h.status == "waiting"

    # 1.2 Spec review: team approves the OpenAPI spec
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"
    assert h.status == "running"

    # -- Endpoint 1: POST /tenants/{id}/subscriptions --
    r = h.submit({
        "endpoint": "POST /tenants/{id}/subscriptions",
        "handler": "subscription_controller.create",
        "db": "INSERT INTO subscriptions (tenant_id, plan, status) VALUES ($1, $2, 'active')",
        "validation": "Pydantic model checks plan enum, verifies tenant exists via FK",
    })
    assert r
    assert r.new_step == "2.2 Write contract tests"
    assert h.step == "2.2 Write contract tests"

    r = h.submit({
        "tests": [
            "test_create_subscription_returns_201",
            "test_create_subscription_invalid_plan_returns_422",
            "test_create_subscription_nonexistent_tenant_returns_404",
        ],
        "schema_validation": "response matches Subscription schema",
    })
    assert r
    assert r.new_step == "2.3 Contract test"
    assert h.step == "2.3 Contract test"

    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # -- Endpoint 2: GET /tenants/{id}/invoices --
    r = h.submit({
        "endpoint": "GET /tenants/{id}/invoices",
        "handler": "invoice_controller.list_by_tenant",
        "db": "SELECT * FROM invoices WHERE tenant_id = $1 ORDER BY due_date DESC LIMIT $2 OFFSET $3",
        "pagination": "cursor-based with ?limit=&after= params",
    })
    assert r
    assert r.new_step == "2.2 Write contract tests"
    assert h.step == "2.2 Write contract tests"

    r = h.submit({
        "tests": ["test_list_invoices_paginated", "test_list_invoices_empty_tenant"],
    })
    assert r
    assert r.new_step == "2.3 Contract test"
    assert h.step == "2.3 Contract test"

    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # -- Endpoint 3: POST /invoices/{id}/payments --
    r = h.submit({
        "endpoint": "POST /invoices/{id}/payments",
        "handler": "payment_controller.create_payment",
        "integration": "Stripe PaymentIntent API via stripe-python SDK",
    })
    assert r
    r = h.submit({"tests": ["test_payment_creates_stripe_intent", "test_payment_idempotency_key"]})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # -- Endpoint 4: GET /usage/metrics --
    r = h.submit({
        "endpoint": "GET /usage/metrics",
        "handler": "usage_controller.get_metrics",
        "db": "SELECT metric_name, SUM(value) FROM usage_events WHERE tenant_id = $1 GROUP BY metric_name",
    })
    assert r
    r = h.submit({"tests": ["test_usage_metrics_aggregation", "test_usage_metrics_date_range_filter"]})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # -- Endpoint 5: POST /webhooks/stripe --
    r = h.submit({
        "endpoint": "POST /webhooks/stripe",
        "handler": "webhook_controller.handle_stripe",
        "signature_verification": "stripe.Webhook.construct_event(payload, sig_header, webhook_secret)",
    })
    assert r
    r = h.submit({"tests": ["test_webhook_signature_valid", "test_webhook_payment_succeeded_updates_invoice"]})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    # Loop exhausted, auto-advance to integration
    assert h.step == "3.1 Integration testing"
    assert h.status == "running"

    # Verify loop_state cleaned after loop exhaustion
    assert "2.0 Endpoint loop" not in (h.state.loop_state or {})

    # 3.1 Integration testing passes
    r = h.submit_goto("3.2 Generate documentation")
    assert r
    assert r.new_step == "3.2 Generate documentation"
    assert h.step == "3.2 Generate documentation"

    # 3.2 Generate Redoc + Swagger UI from the OpenAPI spec
    r = h.submit({
        "tools": ["redoc-cli", "swagger-ui-express"],
        "output": "/docs/api.html",
        "changelog": "v1.0.0 - Initial billing API with 5 endpoints",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_contract_test_fails_retry(harness_factory):
    """Scenario 2: GET /products endpoint fails contract tests twice -- pagination header mismatch then wrong date format."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["GET /products"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Write OpenAPI spec"

    r = h.submit({
        "spec_version": "3.1.0",
        "title": "Product Catalog API",
        "endpoints": ["GET /products with cursor pagination, filtering by category"],
    })
    assert r
    assert r.new_step == "1.2 Spec review"
    assert h.step == "1.2 Spec review"

    # WAIT+LLM: approve first
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # Verify loop first entry
    status = h.get_status()
    assert "[1/" in status["display_path"]

    # Attempt 1: pagination Link header missing from response
    r = h.submit({
        "endpoint": "GET /products",
        "handler": "product_controller.list",
        "db": "SELECT * FROM products WHERE category = $1 LIMIT $2",
        "issue": "Forgot to set Link header for pagination",
    })
    assert r
    assert r.new_step == "2.2 Write contract tests"
    assert h.step == "2.2 Write contract tests"

    r = h.submit({
        "tests": ["test_products_list_returns_link_header", "test_products_list_schema"],
        "failures": "test_products_list_returns_link_header: AssertionError: 'Link' not in response.headers",
    })
    assert r
    assert r.new_step == "2.3 Contract test"
    assert h.step == "2.3 Contract test"

    r = h.submit_goto("2.1 Implement endpoint")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # Attempt 2: added Link header but created_at uses Unix timestamp instead of ISO 8601
    r = h.submit({
        "fix": "Added Link header with rel=next for cursor pagination",
        "remaining_issue": "created_at returned as epoch int instead of ISO 8601 string per spec",
    })
    assert r
    assert r.new_step == "2.2 Write contract tests"
    assert h.step == "2.2 Write contract tests"

    r = h.submit({
        "failures": "test_products_list_schema: jsonschema.ValidationError: 1706745600 is not of type 'string' (format: date-time)",
    })
    assert r
    assert r.new_step == "2.3 Contract test"
    assert h.step == "2.3 Contract test"

    r = h.submit_goto("2.1 Implement endpoint")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"

    # Attempt 3: fixed date serialization, all contract tests pass
    r = h.submit({
        "fix": "Added .isoformat() serialization for all datetime fields in ProductSchema",
        "all_tests_pass": True,
    })
    assert r
    assert r.new_step == "2.2 Write contract tests"
    assert h.step == "2.2 Write contract tests"

    r = h.submit({
        "result": "All 5 contract tests pass: schema validation, pagination headers, date formats",
    })
    assert r
    assert r.new_step == "2.3 Contract test"
    assert h.step == "2.3 Contract test"

    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert h.step == "3.1 Integration testing"


def test_spec_review_rejected(harness_factory):
    """Scenario 3: Inventory API spec rejected -- missing idempotency keys for PUT operations, rewrite required."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["PUT /inventory/{sku}"]})
    r = h.start()
    assert r

    # First spec attempt: missing idempotency headers
    r = h.submit({
        "spec_version": "3.1.0",
        "title": "Warehouse Inventory API",
        "endpoints": ["PUT /inventory/{sku} -- adjust stock levels"],
        "problem": "No Idempotency-Key header defined, PUT can double-decrement stock on retry",
    })
    assert r
    assert r.new_step == "1.2 Spec review"
    assert h.step == "1.2 Spec review"
    assert h.status == "waiting"

    # Reviewer rejects: need idempotency support for stock mutations
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("1.1 Write OpenAPI spec")
    assert r
    assert r.new_step == "1.1 Write OpenAPI spec"
    assert h.step == "1.1 Write OpenAPI spec"
    assert h.status == "running"

    # Rewrite spec with Idempotency-Key header and optimistic locking via ETag
    r = h.submit({
        "spec_version": "3.1.0",
        "title": "Warehouse Inventory API v2",
        "changes": [
            "Added Idempotency-Key request header (required for PUT/POST)",
            "Added ETag/If-Match for optimistic concurrency on stock updates",
            "Added 409 Conflict response for concurrent modification",
        ],
    })
    assert r
    assert r.new_step == "1.2 Spec review"
    assert h.step == "1.2 Spec review"

    # Approved on second attempt
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"


def test_integration_fails_back_to_loop(harness_factory):
    """Scenario 4: Auth + Orders API integration fails due to JWT scope mismatch between services."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["POST /auth/token", "GET /orders"]})
    r = h.start()
    assert r

    r = h.submit({
        "spec_version": "3.1.0",
        "title": "E-Commerce Gateway API",
        "security": "OAuth2 with JWT bearer tokens, scopes: orders:read, orders:write",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert h.step == "2.1 Implement endpoint"

    # Endpoint 1: POST /auth/token
    r = h.submit({"endpoint": "POST /auth/token", "handler": "auth.issue_jwt", "scopes": ["orders:read", "orders:write"]})
    assert r
    r = h.submit({"tests": ["test_token_includes_scopes", "test_token_expiry_1h"]})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    # Endpoint 2: GET /orders
    r = h.submit({"endpoint": "GET /orders", "handler": "orders.list", "required_scope": "orders:read"})
    assert r
    r = h.submit({"tests": ["test_orders_requires_bearer", "test_orders_returns_list"]})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    assert h.step == "3.1 Integration testing"

    # Integration fails: auth service issues scope "order:read" (missing 's') but orders service expects "orders:read"
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"
    assert h.status == "running"

    # Fix both endpoints with consistent scope naming
    r = h.submit({"endpoint": "POST /auth/token", "fix": "Corrected scope from 'order:read' to 'orders:read'"})
    assert r
    r = h.submit({"tests": ["test_token_scope_matches_orders_service"]})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    r = h.submit({"endpoint": "GET /orders", "fix": "Added scope validation error message with expected vs actual"})
    assert r
    r = h.submit({"tests": ["test_orders_rejects_wrong_scope_with_403"]})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    assert h.step == "3.1 Integration testing"

    r = h.submit_goto("3.2 Generate documentation")
    assert r
    assert r.new_step == "3.2 Generate documentation"
    assert h.step == "3.2 Generate documentation"

    r = h.submit({"output": "Generated Swagger UI with OAuth2 flow documentation"})
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_skip_documentation(harness_factory):
    """Scenario 5: Internal health-check endpoint -- skip docs generation since it is not public-facing."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["GET /healthz"]})
    r = h.start()
    assert r

    r = h.submit({
        "spec_version": "3.1.0",
        "title": "Internal Health Check API",
        "note": "Kubernetes liveness/readiness probe -- not exposed to external consumers",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    r = h.submit({
        "endpoint": "GET /healthz",
        "handler": "health.check",
        "checks": ["PostgreSQL ping", "Redis ping", "RabbitMQ connection"],
        "response": {"status": "ok", "uptime_seconds": 86400, "checks": {"db": "ok", "cache": "ok", "queue": "ok"}},
    })
    assert r
    r = h.submit({"tests": ["test_healthz_all_services_up", "test_healthz_db_down_returns_503"]})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    assert h.step == "3.1 Integration testing"

    r = h.submit_goto("3.2 Generate documentation")
    assert r
    assert r.new_step == "3.2 Generate documentation"
    assert h.step == "3.2 Generate documentation"

    r = h.skip("Internal-only endpoint, not included in public API docs")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_empty_endpoint_list(harness_factory):
    """Scenario 6: Spec-only API review -- no endpoints to implement yet, just validating the contract shape."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": []})
    r = h.start()
    assert r

    r = h.submit({
        "spec_version": "3.1.0",
        "title": "Payment Gateway API v2 (Draft)",
        "note": "Design-phase only -- endpoints will be added after stakeholder approval",
        "schemas_defined": ["PaymentIntent", "Refund", "Dispute", "Webhook"],
    })
    assert r
    # WAIT+LLM: approve first
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    # Empty loop auto-advances past the loop
    assert h.step == "3.1 Integration testing"
    assert h.status == "running"


def test_stop_then_resume(harness_factory):
    """Scenario 7: Stop during spec review for a Kafka consumer API while waiting for schema registry team."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["POST /consumers/subscribe"]})
    r = h.start()
    assert r

    r = h.submit({
        "spec_version": "3.1.0",
        "title": "Kafka Consumer Management API",
        "note": "Depends on schema registry team finalizing Avro schemas -- blocking on review",
        "endpoints": ["POST /consumers/subscribe -- subscribe a consumer group to a topic"],
    })
    assert r
    assert r.new_step == "1.2 Spec review"
    assert h.step == "1.2 Spec review"

    # Stop: waiting for schema registry team to finalize Avro schemas
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "1.2 Spec review"

    # Schema registry team finished -- resume
    r = h.resume()
    assert r
    assert h.status == "waiting"
    assert h.step == "1.2 Spec review"

    # Now approve with finalized schema info
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"


def test_complete_then_reset(harness_factory):
    """Scenario 8: Ship Notification API v1, then reset to start v2 with WebSocket support."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["POST /notifications/send"]})
    r = h.start()
    assert r

    r = h.submit({
        "spec_version": "3.1.0",
        "title": "Notification API v1",
        "endpoints": ["POST /notifications/send -- send push/email/SMS via unified interface"],
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    r = h.submit({
        "endpoint": "POST /notifications/send",
        "handler": "notification.dispatch",
        "channels": ["email_ses", "push_fcm", "sms_twilio"],
    })
    assert r
    r = h.submit({"tests": ["test_send_email_via_ses", "test_send_push_via_fcm", "test_invalid_channel_422"]})
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    r = h.submit_goto("3.2 Generate documentation")
    assert r
    r = h.submit({"output": "Notification API v1 docs published to developer portal"})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # v1 shipped -- cannot add more endpoints
    r = h.submit({})
    assert not r

    # Reset to start v2 with WebSocket real-time notifications
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Write OpenAPI spec"
    assert h.status == "running"


def test_modify_yaml_add_validation_step(harness_factory):
    """Scenario 9: Hot-reload YAML to add spectral lint step after security audit requires OpenAPI validation."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["GET /patients/{id}"]})
    r = h.start()
    assert r

    r = h.submit({
        "spec_version": "3.1.0",
        "title": "Healthcare Patient Records API",
        "compliance": "HIPAA-compliant, requires security review",
    })
    assert r
    assert r.new_step == "1.2 Spec review"
    assert h.step == "1.2 Spec review"

    # Security audit requires automated spec validation with Spectral
    yaml_content = """name: API-First Development
description: OpenAPI spec first, endpoint loop, contract test 2-way, integration fallback

steps:
  - 1.1 Write OpenAPI spec

  - 1.2 Spec review:
      type: wait
      next:
        - if: "spec is approved"
          go: 1.3 Validate spec
        - go: 1.1 Write OpenAPI spec

  - 1.3 Validate spec:
      next: 2.0 Endpoint loop

  - 2.0 Endpoint loop:
      iterate: "endpoints"
      children:
        - 2.1 Implement endpoint
        - 2.2 Write contract tests
        - 2.3 Contract test:
            next:
              - if: "contract test passes"
                go: 2.0 Endpoint loop
              - go: 2.1 Implement endpoint

  - 3.1 Integration testing:
      next:
        - if: "all endpoints work together"
          go: 3.2 Generate documentation
        - go: 2.0 Endpoint loop

  - 3.2 Generate documentation

  - Done:
      type: terminate
      reason: API fully implemented and documented
"""
    h.reload_yaml(yaml_content)

    r = h.goto("1.3 Validate spec")
    assert r
    assert r.new_step == "1.3 Validate spec"
    assert h.step == "1.3 Validate spec"
    assert h.status == "running"

    r = h.submit({
        "tool": "spectral lint openapi.yaml",
        "rules": "HIPAA ruleset: require-auth-on-all-operations, no-pii-in-query-params",
        "result": "0 errors, 0 warnings",
    })
    assert r
    assert r.new_step == "2.1 Implement endpoint"
    assert h.step == "2.1 Implement endpoint"


def test_goto_integration(harness_factory):
    """Scenario 10: Jump to integration testing -- endpoints already implemented in a previous sprint, just need E2E validation."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["GET /metrics", "POST /alerts"]})
    r = h.start()
    assert r

    r = h.submit({
        "spec_version": "3.1.0",
        "title": "Monitoring & Alerting API",
        "note": "Endpoints already implemented in sprint 14, need integration testing",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Endpoint loop")
    assert r

    # Skip individual endpoint work -- jump to integration
    r = h.goto("3.1 Integration testing")
    assert r
    assert r.new_step == "3.1 Integration testing"
    assert h.step == "3.1 Integration testing"
    assert h.status == "running"

    r = h.submit_goto("3.2 Generate documentation")
    assert r
    assert r.new_step == "3.2 Generate documentation"
    assert h.step == "3.2 Generate documentation"

    r = h.submit({
        "output": "Published Monitoring API docs to Backstage developer portal",
        "includes": ["Prometheus metric types", "Alert rule examples", "Grafana dashboard links"],
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ═══════════════════════════════════════════════════════
# Dimension tests: Data accumulation
# ═══════════════════════════════════════════════════════

def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()

    h.submit({"spec": "openapi v3"})
    data = h.state.data
    assert "1.1 Write OpenAPI spec" in data
    assert data["1.1 Write OpenAPI spec"]["spec"] == "openapi v3"

    h.approve()
    h.submit_goto("2.0 Endpoint loop")
    h.submit({"endpoint": "GET /users"})
    data = h.state.data
    assert "2.1 Implement endpoint" in data
    assert data["2.1 Implement endpoint"]["endpoint"] == "GET /users"


def test_s2_data_after_contract_retry(harness_factory):
    """Data persists after retry loop back to implement."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    _enter_endpoint_loop(h)

    h.submit({"impl": "v1"})
    h.submit({"tests": "contract_v1"})
    h.submit_goto("2.1 Implement endpoint")

    h.submit({"impl": "v2"})
    data = h.state.data
    assert data["2.1 Implement endpoint"]["impl"] == "v2"


# ═══════════════════════════════════════════════════════
# Dimension tests: History audit trail
# ═══════════════════════════════════════════════════════

def test_s1_history_audit_trail(harness_factory):
    """After walkthrough, history contains expected action sequence."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.submit({})
    h.approve()
    h.submit_goto("2.0 Endpoint loop")
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Endpoint loop")
    h.submit_goto("3.2 Generate documentation")
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "approve" in actions
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_s3_history_shows_reject_path(harness_factory):
    """History records the reject path through spec review."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.submit({})
    h.approve()
    h.submit_goto("1.1 Write OpenAPI spec")

    history = h.get_history(20)
    actions = [e["action"] for e in history]
    assert "approve" in actions
    assert "submit" in actions


# ═══════════════════════════════════════════════════════
# Dimension tests: Cross-executor recovery
# ═══════════════════════════════════════════════════════

def test_cross_executor_at_spec_review(harness_factory):
    """Close at spec review, reopen, state persists."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    _walk_to_spec_review(h)

    h.new_executor()

    assert h.step == "1.2 Spec review"
    assert h.status == "waiting"

    h.approve()
    r = h.submit_goto("2.0 Endpoint loop")
    assert r
    assert h.step == "2.1 Implement endpoint"


def test_cross_executor_mid_loop(harness_factory):
    """Close mid-loop, reopen, loop state preserved."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1", "e2"]})
    _enter_endpoint_loop(h)

    h.submit({"impl": "v1"})
    assert h.step == "2.2 Write contract tests"

    h.new_executor()

    assert h.step == "2.2 Write contract tests"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Endpoint loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.goto("3.2 Generate documentation")
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

def test_node_validates_endpoint(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
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

    r = h.submit({"endpoint": "GET /users"})
    assert r
    assert r.new_step == "2.2 Write contract tests"


def test_node_validates_contract_tests(harness_factory):
    """Validate node on contract test step."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    _enter_endpoint_loop(h)
    h.submit({})
    assert h.step == "2.2 Write contract tests"

    h.register_node(
        "2.2 Write contract tests",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("test_count", 0) > 0 else "no tests written",
        ),
    )

    r = h.submit({"test_count": 0})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"test_count": 3})
    assert r


# ═══════════════════════════════════════════════════════
# Dimension tests: Node archival
# ═══════════════════════════════════════════════════════

def test_node_archives_endpoints(harness_factory):
    """Archive node writes each endpoint to SQLite."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1", "e2"]})
    _enter_endpoint_loop(h)

    h.register_node(
        "2.1 Implement endpoint",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"name": "string", "method": "string"}},
            archive={"table": "endpoints_impl"},
        ),
    )

    for _i in range(2):
        h.submit({"name": f"ep_{_i}", "method": "GET"})
        h.submit({})
        h.submit_goto("2.0 Endpoint loop")

    rows = h.get_archived_rows("endpoints_impl")
    assert len(rows) == 2
    assert rows[0]["name"] == "ep_0"
    assert rows[1]["name"] == "ep_1"


# ═══════════════════════════════════════════════════════
# Dimension tests: Error boundaries
# ═══════════════════════════════════════════════════════

def test_submit_on_waiting_fails(harness_factory):
    """Submit on a waiting step returns failure."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    _walk_to_spec_review(h)
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.goto("3.2 Generate documentation")
    h.submit({})
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.goto("3.2 Generate documentation")
    h.submit({})
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_resume_on_running_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ═══════════════════════════════════════════════════════
# Generic / cross-cutting tests
# ═══════════════════════════════════════════════════════

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.submit({"spec": "openapi v3"})

    h.save_checkpoint("at_spec_review")

    h.approve()
    h.submit_goto("2.0 Endpoint loop")
    assert h.step == "2.1 Implement endpoint"

    restored = h.load_checkpoint("at_spec_review")
    assert restored is not None
    assert restored.current_step == "1.2 Spec review"
    assert "1.1 Write OpenAPI spec" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    assert h.step == "1.1 Write OpenAPI spec"

    r = h.retry()
    assert r
    assert h.step == "1.1 Write OpenAPI spec"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_back_returns_to_previous(harness_factory):
    """Back returns to the previously visited step."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Spec review"

    r = h.back()
    assert r
    assert h.step == "1.1 Write OpenAPI spec"


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Write OpenAPI spec"


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["a", "b", "c"]})
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
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["e1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Spec review"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "1.2 Spec review"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"


# ═══════════════════════════════════════════════════════
# Turing machine condition checker tests
# ═══════════════════════════════════════════════════════

def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["GET /users"]})
    h.start()
    h.register_node(
        "1.1 Write OpenAPI spec",
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
    h = harness_factory("p3-api-first.yaml", loop_data={"endpoints": ["GET /users"]})
    h.start()
    h.register_node(
        "1.1 Write OpenAPI spec",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
