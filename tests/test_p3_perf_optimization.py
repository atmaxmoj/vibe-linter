"""Performance Optimization workflow tests."""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# ─── Helpers ───

def _enter_hotspot_loop(h):
    """Start -> 1.1 -> 1.2 -> enter hotspot loop at 2.1."""
    h.start()
    h.submit({})   # 1.1 -> 1.2
    h.submit({})   # 1.2 -> 2.0 -> 2.1
    assert h.step == "2.1 Analyze hotspot"
    assert h.status == "running"


def _do_one_hotspot(h):
    """Complete one hotspot cycle: 2.1 -> 2.2 -> 2.3."""
    h.submit({})   # 2.1 -> 2.2
    h.submit({})   # 2.2 -> 2.3
    assert h.step == "2.3 Benchmark"


# ═══════════════════════════════════════════════════════
# Existing scenarios (unchanged)
# ═══════════════════════════════════════════════════════

def test_optimize_three_hotspots(harness_factory):
    """Scenario 1: E-commerce API p99 from 1.2s to 200ms -- fix N+1 query, add Redis cache, optimize JSON serialization."""
    h = harness_factory(
        "p3-perf-optimization.yaml",
        loop_data={"hotspots": [
            "N+1 query in order listing",
            "Missing cache for product catalog",
            "Slow JSON serialization",
        ]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Profile application"
    assert h.status == "running"

    # 1.1 Profile the application
    r = h.submit({
        "tool": "py-spy + pgBadger + Datadog APM",
        "baseline": {
            "p50_latency": "320ms",
            "p99_latency": "1.2s",
            "throughput": "450 req/s",
            "target_p99": "200ms",
            "target_throughput": "1200 req/s",
        },
        "top_endpoints": [
            {"path": "GET /orders", "p99": "1.1s", "calls_per_min": 2400},
            {"path": "GET /products", "p99": "800ms", "calls_per_min": 5200},
            {"path": "GET /products/{id}", "p99": "400ms", "calls_per_min": 8100},
        ],
    })
    assert r
    assert r.new_step == "1.2 Identify hotspots"
    assert h.step == "1.2 Identify hotspots"

    # 1.2 Identify hotspots from profiling data
    r = h.submit({
        "hotspots": [
            {"name": "N+1 query in order listing", "impact": "60% of p99 tail", "root_cause": "ORM lazy-loads order items per order"},
            {"name": "Missing cache for product catalog", "impact": "25% of total load", "root_cause": "Every request hits PostgreSQL"},
            {"name": "Slow JSON serialization", "impact": "15% CPU time", "root_cause": "Python json.dumps on large nested objects"},
        ],
    })
    assert r
    assert r.new_step == "2.1 Analyze hotspot"
    assert h.step == "2.1 Analyze hotspot"

    # -- Hotspot 1: N+1 query --
    r = h.submit({
        "hotspot": "N+1 query in order listing",
        "analysis": "GET /orders executes 1 + N queries (1 for orders, N for items). For 50 orders: 51 queries, 800ms",
        "plan": "Use SQLAlchemy selectinload() to eager-load order items in 2 queries total",
    })
    assert r
    assert r.new_step == "2.2 Implement optimization"
    assert h.step == "2.2 Implement optimization"

    r = h.submit({
        "change": "Added .options(selectinload(Order.items)) to order listing query",
        "queries_before": 51,
        "queries_after": 2,
        "file": "src/repositories/order_repository.py",
    })
    assert r
    assert r.new_step == "2.3 Benchmark"
    assert h.step == "2.3 Benchmark"

    r = h.submit_goto("2.0 Hotspot loop")
    assert r
    assert r.new_step == "2.1 Analyze hotspot"
    assert h.step == "2.1 Analyze hotspot"

    # -- Hotspot 2: Missing cache --
    r = h.submit({
        "hotspot": "Missing cache for product catalog",
        "analysis": "GET /products hits PostgreSQL every time. Product data changes once per hour but is read 5200 times/min",
        "plan": "Redis cache-aside with 5min TTL, cache key: products:{category}:{page}",
    })
    assert r
    r = h.submit({
        "change": "Added Redis cache-aside pattern with 5min TTL for product listings",
        "cache_hit_rate": "Expected 95%+ after warm-up",
        "config": {"host": "redis-cluster.internal", "max_connections": 50, "ttl": 300},
    })
    assert r
    r = h.submit_goto("2.0 Hotspot loop")
    assert r
    assert r.new_step == "2.1 Analyze hotspot"
    assert h.step == "2.1 Analyze hotspot"

    # -- Hotspot 3: JSON serialization --
    r = h.submit({
        "hotspot": "Slow JSON serialization",
        "analysis": "json.dumps takes 15ms for large product responses with 200+ nested items",
        "plan": "Replace stdlib json with orjson (10-50x faster for complex objects)",
    })
    assert r
    r = h.submit({
        "change": "Replaced json.dumps with orjson.dumps, added orjson to requirements",
        "serialization_time_before": "15ms",
        "serialization_time_after": "0.3ms",
    })
    assert r
    r = h.submit_goto("2.0 Hotspot loop")
    assert r

    assert h.step == "3.1 Final benchmark"

    # Verify loop_state cleaned after loop exhaustion
    assert "2.0 Hotspot loop" not in (h.state.loop_state or {})

    # 3.1 Final benchmark: all targets met
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_cant_optimize_enough_keep_trying(harness_factory):
    """Scenario 2: PostgreSQL query planner ignores index -- 5 attempts to get p99 under 50ms."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["Sequential scan on orders table"]})
    r = h.start()
    assert r

    # 1.1 Profile: pg_stat_statements reveals a sequential scan
    r = h.submit({
        "tool": "pg_stat_statements + EXPLAIN ANALYZE",
        "baseline": {
            "query": "SELECT * FROM orders WHERE tenant_id = $1 AND status = 'pending' ORDER BY created_at DESC LIMIT 20",
            "avg_time": "340ms",
            "p99_time": "1.8s",
            "rows_scanned": "12M",
            "target_p99": "50ms",
        },
    })
    assert r
    # Enter loop directly (auto-advances to first child)
    r = h.submit({
        "hotspots": [{"name": "Sequential scan on orders table", "impact": "90% of slow queries", "root_cause": "Missing composite index + query planner choosing seq scan"}],
    })
    assert r
    assert r.new_step == "2.1 Analyze hotspot"
    assert h.step == "2.1 Analyze hotspot"

    # Verify loop first entry
    status = h.get_status()
    assert "[1/" in status["display_path"]

    # First attempt: add B-tree index (starting from 2.1)
    r = h.submit({
        "hotspot": "Sequential scan on orders table",
        "analysis": "EXPLAIN shows Seq Scan cost=0.00..287431.00 rows=12M. No index on (tenant_id, status, created_at)",
        "plan": "CREATE INDEX CONCURRENTLY idx_orders_tenant_status_created ON orders(tenant_id, status, created_at DESC)",
    })
    assert r
    assert r.new_step == "2.2 Implement optimization"
    assert h.step == "2.2 Implement optimization"

    r = h.submit({
        "change": "Created composite B-tree index on (tenant_id, status, created_at DESC)",
        "migration": "V47__add_orders_composite_index.sql",
        "index_size": "2.1GB",
    })
    assert r
    assert r.new_step == "2.3 Benchmark"
    assert h.step == "2.3 Benchmark"

    # Benchmark 1 FAILS: planner still prefers seq scan on wide tenant_id ranges
    r = h.submit_goto("2.2 Implement optimization")
    assert r
    assert r.new_step == "2.2 Implement optimization"
    assert h.step == "2.2 Implement optimization"

    # Attempt 2: SET enable_seqscan=off hint -- still fails (starting from 2.2)
    r = h.submit({
        "change": "Added SET LOCAL enable_seqscan = off before query execution",
        "note": "Temporary workaround to force index usage",
        "p99_after": "120ms -- better but still above 50ms target",
    })
    assert r
    assert r.new_step == "2.3 Benchmark"
    assert h.step == "2.3 Benchmark"

    r = h.submit_goto("2.2 Implement optimization")
    assert r
    assert r.new_step == "2.2 Implement optimization"
    assert h.step == "2.2 Implement optimization"

    # Attempt 3: partial index -- still fails
    r = h.submit({
        "change": "Replaced full index with partial: WHERE status IN ('pending','processing')",
        "index_size_after": "340MB (was 2.1GB)",
        "p99_after": "85ms -- closer but not under 50ms",
    })
    assert r
    assert r.new_step == "2.3 Benchmark"
    assert h.step == "2.3 Benchmark"

    r = h.submit_goto("2.2 Implement optimization")
    assert r
    assert r.new_step == "2.2 Implement optimization"
    assert h.step == "2.2 Implement optimization"

    # Attempt 4: covering index with INCLUDE -- still fails
    r = h.submit({
        "change": "INCLUDE (id, total_amount) to make index-only scan possible",
        "p99_after": "62ms -- almost there, IO on large tenants still spikes",
    })
    assert r
    assert r.new_step == "2.3 Benchmark"
    assert h.step == "2.3 Benchmark"

    r = h.submit_goto("2.2 Implement optimization")
    assert r
    assert r.new_step == "2.2 Implement optimization"
    assert h.step == "2.2 Implement optimization"

    # Attempt 5: table partitioning by tenant_id range -- PASSES
    r = h.submit({
        "change": "Partitioned orders table by tenant_id range (8 partitions) + covering partial index per partition",
        "p99_after": "28ms",
        "rows_scanned_after": "15K (was 12M)",
        "migration": "V48__partition_orders_by_tenant.sql",
    })
    assert r
    assert r.new_step == "2.3 Benchmark"
    assert h.step == "2.3 Benchmark"

    r = h.submit_goto("2.0 Hotspot loop")
    assert r
    assert h.step == "3.1 Final benchmark"


def test_architecture_change_stop_switch(harness_factory):
    """Scenario 3: Monolith cannot scale -- stop to switch to microservices decomposition SOP."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["Connection pool exhaustion under load"]})
    r = h.start()
    assert r

    # 1.1 Profile: k6 load test shows connection pool saturation
    r = h.submit({
        "tool": "k6 + Grafana + PgBouncer stats",
        "baseline": {
            "concurrent_users": 500,
            "connection_pool_size": 20,
            "pool_wait_time_p99": "4.2s",
            "error_rate": "12% (connection timeout)",
        },
    })
    assert r
    # Enter loop directly (auto-advances to first child)
    r = h.submit({
        "hotspots": [{"name": "Connection pool exhaustion under load", "impact": "12% error rate at 500 concurrent users", "root_cause": "Single DB, all services share 20-connection pool"}],
    })
    assert r
    # 2.1 Analyze
    r = h.submit({
        "hotspot": "Connection pool exhaustion under load",
        "analysis": "Monolith uses single PostgreSQL with 20 connections shared by orders, inventory, notifications, and analytics. Analytics queries hold connections for 2-5s blocking OLTP.",
        "plan": "Separate read replicas + connection pool per service module",
    })
    assert r
    assert r.new_step == "2.2 Implement optimization"
    assert h.step == "2.2 Implement optimization"

    # Realize optimization within monolith is insufficient -- need microservices decomposition
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Implement optimization"


def test_skip_hotspot(harness_factory):
    """Scenario 4: Skip GC tuning (risk too high) -- optimize only the connection pool."""
    h = harness_factory(
        "p3-perf-optimization.yaml",
        loop_data={"hotspots": ["GC pause spikes", "Thread pool saturation"]},
    )
    r = h.start()
    assert r

    # 1.1 Profile
    r = h.submit({
        "tool": "async-profiler + GC logs + Prometheus JMX exporter",
        "baseline": {
            "gc_pause_p99": "450ms",
            "thread_pool_queue_depth": 2400,
            "target_gc_pause": "50ms",
            "target_queue_depth": "<100",
        },
    })
    assert r
    # 1.2 Identify hotspots
    r = h.submit({
        "hotspots": [
            {"name": "GC pause spikes", "impact": "p99 latency spikes every 30s", "root_cause": "G1GC old-gen promotion with 32GB heap"},
            {"name": "Thread pool saturation", "impact": "Request queueing under 200 req/s", "root_cause": "Tomcat thread pool at 200 threads, blocking IO on downstream calls"},
        ],
    })
    assert r
    # 2.1 Analyze hotspot 1: GC
    r = h.submit({
        "hotspot": "GC pause spikes",
        "analysis": "G1GC mixed collections on 32GB heap causing 200-450ms pauses. Would require switching to ZGC or Shenandoah.",
        "plan": "Switch to ZGC (-XX:+UseZGC) and tune heap regions",
    })
    assert r
    assert r.new_step == "2.2 Implement optimization"
    assert h.step == "2.2 Implement optimization"

    # Skip: GC tuning requires JDK upgrade from 11 to 17 -- too risky for this sprint
    r = h.skip("Requires JDK 11 -> 17 upgrade; out of scope for current sprint, tracked in PERF-892")
    assert r
    assert r.new_step == "2.3 Benchmark"
    assert h.step == "2.3 Benchmark"

    r = h.submit_goto("2.0 Hotspot loop")
    assert r
    # 2.1 Analyze hotspot 2: thread pool
    r = h.submit({
        "hotspot": "Thread pool saturation",
        "analysis": "200 Tomcat threads blocked on synchronous HTTP calls to payment/inventory services. 80% time in socket read.",
        "plan": "Replace RestTemplate with WebClient (non-blocking) + virtual threads for remaining blocking calls",
    })
    assert r
    r = h.submit({
        "change": "Migrated 12 downstream calls from RestTemplate to WebClient reactive; Tomcat thread pool reduced to 50",
        "queue_depth_after": 45,
        "p99_after": "120ms (excluding GC pauses)",
    })
    assert r
    r = h.submit_goto("2.0 Hotspot loop")
    assert r

    assert h.step == "3.1 Final benchmark"

    # 3.1 Final benchmark passes (GC pauses acceptable for now)
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_final_benchmark_fails_back_to_loop(harness_factory):
    """Scenario 5: Final k6 benchmark misses SLA -- re-optimize both Redis and DNS hotspots."""
    h = harness_factory(
        "p3-perf-optimization.yaml",
        loop_data={"hotspots": ["Redis pipeline underuse", "DNS resolution per request"]},
    )
    r = h.start()
    assert r

    # 1.1 Profile
    r = h.submit({
        "tool": "k6 + Prometheus + redis-cli --latency",
        "baseline": {"p99": "380ms", "throughput": "800 req/s", "target_p99": "100ms", "target_throughput": "3000 req/s"},
    })
    assert r
    # 1.2 Identify
    r = h.submit({
        "hotspots": [
            {"name": "Redis pipeline underuse", "impact": "RTT overhead on 15 sequential GET calls", "root_cause": "No pipelining"},
            {"name": "DNS resolution per request", "impact": "50ms added per external API call", "root_cause": "No DNS caching, resolve on every HTTP request"},
        ],
    })
    assert r

    # -- Round 1: optimize both hotspots --
    # Hotspot 1: Redis pipelining
    r = h.submit({
        "hotspot": "Redis pipeline underuse",
        "analysis": "Each request makes 15 sequential Redis GETs (session, cart, user prefs, feature flags). Total RTT: 15 * 0.8ms = 12ms",
        "plan": "Pipeline all Redis reads into single round-trip using redis.pipeline()",
    })
    assert r
    r = h.submit({
        "change": "Batched 15 GETs into pipeline(), latency reduced from 12ms to 1.2ms per request",
    })
    assert r
    r = h.submit_goto("2.0 Hotspot loop")
    assert r

    # Hotspot 2: DNS caching
    r = h.submit({
        "hotspot": "DNS resolution per request",
        "analysis": "httpx resolves payment-api.stripe.com on every call. Average DNS lookup: 50ms",
        "plan": "Enable httpx connection pooling with DNS cache TTL=300s",
    })
    assert r
    r = h.submit({
        "change": "Configured httpx.AsyncClient with limits=Limits(max_connections=100) and local DNS cache",
    })
    assert r
    r = h.submit_goto("2.0 Hotspot loop")
    assert r

    assert h.step == "3.1 Final benchmark"

    # Final benchmark FAILS: p99 dropped to 150ms but target is 100ms
    r = h.submit_goto("2.0 Hotspot loop")
    assert r
    assert r.new_step == "2.1 Analyze hotspot"
    assert h.step == "2.1 Analyze hotspot"
    assert h.status == "running"

    # -- Round 2: deeper optimization on same hotspots --
    # Redis: switch to cluster mode with read replicas
    r = h.submit({
        "hotspot": "Redis pipeline underuse",
        "analysis": "Pipeline helped but single Redis node at 85% CPU. Need cluster mode for read scaling.",
        "plan": "Migrate to Redis Cluster with 3 masters + 3 replicas, route reads to replicas",
    })
    assert r
    r = h.submit({
        "change": "Deployed Redis Cluster 6-node (3M+3R), read commands route to replicas via READONLY",
        "p99_redis_after": "0.4ms",
    })
    assert r
    r = h.submit_goto("2.0 Hotspot loop")
    assert r

    # DNS: switch to service mesh with sidecar proxy
    r = h.submit({
        "hotspot": "DNS resolution per request",
        "analysis": "Local DNS cache helps but TTL expiry causes periodic 50ms spikes",
        "plan": "Use Envoy sidecar with persistent connections to upstream, zero DNS in hot path",
    })
    assert r
    r = h.submit({
        "change": "Added Envoy sidecar with cluster discovery, upstream connections pre-warmed",
        "dns_latency_after": "0ms (handled by sidecar)",
    })
    assert r
    r = h.submit_goto("2.0 Hotspot loop")
    assert r

    assert h.step == "3.1 Final benchmark"

    # Final benchmark passes: p99=62ms, throughput=3400 req/s
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_stop_then_resume(harness_factory):
    """Scenario 6: Stop during profiling to wait for production traffic window, then resume."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["Memory leak in worker pool"]})
    r = h.start()
    assert r

    # 1.1 Profile: initial profiling done with staging data
    r = h.submit({
        "tool": "Datadog Continuous Profiler + heaptrack",
        "baseline": {
            "rss_growth_per_hour": "120MB",
            "p99_after_6h": "2.4s (vs 200ms at startup)",
            "note": "Need production traffic patterns to reproduce -- waiting for US-East peak hours",
        },
    })
    assert r
    assert r.new_step == "1.2 Identify hotspots"
    assert h.step == "1.2 Identify hotspots"

    # Stop: waiting for production peak traffic window (US-East 10am-2pm)
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "1.2 Identify hotspots"

    # Resume after production profiling completed
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "1.2 Identify hotspots"

    # 1.2 Identify with production data
    r = h.submit({
        "hotspots": [{"name": "Memory leak in worker pool", "impact": "OOM kill every 8h, 120MB/h RSS growth", "root_cause": "Celery worker prefork pool leaks DB connections on task timeout"}],
    })
    assert r
    # 2.1 Analyze
    r = h.submit({
        "hotspot": "Memory leak in worker pool",
        "analysis": "Celery prefork workers hold DB connections that are not returned on SoftTimeLimitExceeded. tracemalloc shows 50MB unreachable Connection objects after 4h",
        "plan": "Wrap task execution in connection context manager, add worker_max_tasks_per_child=1000",
    })
    assert r
    # 2.2 Implement
    r = h.submit({
        "change": "Added connection cleanup in task finally block + CELERY_WORKER_MAX_TASKS_PER_CHILD=1000",
        "rss_growth_after": "2MB/h (stable, expected GC churn)",
    })
    assert r
    # 2.3 Benchmark passes
    r = h.submit_goto("2.0 Hotspot loop")
    assert r
    # 3.1 Final benchmark
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_empty_hotspot_list(harness_factory):
    """Scenario 7: Application already optimized -- profiling reveals no hotspots, skip straight to final benchmark."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": []})
    r = h.start()
    assert r

    # 1.1 Profile: everything within SLA
    r = h.submit({
        "tool": "py-spy + pgBadger + Grafana",
        "baseline": {
            "p50": "12ms", "p99": "45ms", "throughput": "4200 req/s",
            "cpu_utilization": "35%", "memory_utilization": "52%",
            "note": "All endpoints within SLA after last quarter's optimization sprint",
        },
    })
    assert r
    # 1.2 Identify hotspots: none found
    r = h.submit({
        "hotspots": [],
        "conclusion": "No hotspots identified. All endpoints under 50ms p99. CPU and memory well below thresholds.",
    })
    assert r

    assert h.step == "3.1 Final benchmark"
    assert h.status == "running"


def test_complete_then_reset(harness_factory):
    """Scenario 8: Optimize GraphQL resolver N+1 -- then reset for v2 with federation."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["GraphQL resolver N+1"]})
    r = h.start()
    assert r

    # 1.1 Profile
    r = h.submit({
        "tool": "Apollo Studio tracing + pg_stat_statements",
        "baseline": {"p99": "900ms", "query": "{ orders { items { product { name } } } }", "sql_queries_per_request": 147},
    })
    assert r
    # 1.2 Identify
    r = h.submit({
        "hotspots": [{"name": "GraphQL resolver N+1", "impact": "147 SQL queries for single orders query", "root_cause": "DataLoader not configured for product resolver"}],
    })
    assert r
    # 2.1 Analyze
    r = h.submit({
        "hotspot": "GraphQL resolver N+1",
        "analysis": "Product resolver fires per-item, each executing SELECT * FROM products WHERE id = $1",
        "plan": "Add DataLoader for product resolver with batch function using WHERE id = ANY($1)",
    })
    assert r
    # 2.2 Implement
    r = h.submit({
        "change": "Added ProductLoader DataLoader, batch-loads products in single query. 147 queries -> 3 queries",
        "p99_after": "85ms",
    })
    assert r
    # 2.3 Benchmark passes
    r = h.submit_goto("2.0 Hotspot loop")
    assert r
    # 3.1 Final benchmark
    r = h.submit_goto("Done")
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Submit on done should fail
    r = h.submit({})
    assert not r

    # Reset for v2: switching to Apollo Federation with subgraph optimization
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Profile application"
    assert h.status == "running"


def test_goto(harness_factory):
    """Scenario 9: Ops already applied optimizations in prod -- jump to final benchmark to validate."""
    h = harness_factory(
        "p3-perf-optimization.yaml",
        loop_data={"hotspots": ["TCP keepalive tuning", "Nginx worker_connections"]},
    )
    r = h.start()
    assert r

    # 1.1 Profile
    r = h.submit({
        "tool": "wrk2 + ss -tnp + netstat",
        "baseline": {"p99": "320ms", "time_wait_sockets": 12000, "target_p99": "80ms"},
        "note": "Ops team already applied sysctl tuning and Nginx config in production last night",
    })
    assert r
    # 1.2 Identify (for records)
    r = h.submit({
        "hotspots": [
            {"name": "TCP keepalive tuning", "impact": "12K TIME_WAIT sockets", "root_cause": "Default kernel tcp_tw_reuse=0"},
            {"name": "Nginx worker_connections", "impact": "Connection queueing at 1024 limit", "root_cause": "Default worker_connections=1024"},
        ],
        "note": "Both already fixed by ops -- skipping to final benchmark",
    })
    assert r

    # Jump directly to final benchmark (ops already applied changes)
    r = h.goto("3.1 Final benchmark")
    assert r
    assert r.new_step == "3.1 Final benchmark"
    assert h.step == "3.1 Final benchmark"
    assert h.status == "running"

    # Verify the ops changes worked
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_back(harness_factory):
    """Scenario 10: Re-profile after discovering wrong baseline -- back to fix profiling methodology."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["Slow PDF generation"]})
    r = h.start()
    assert r

    # 1.1 Profile with wrong methodology (cold cache, no connection pooling)
    r = h.submit({
        "tool": "ab + time",
        "baseline": {"p99": "4.5s", "throughput": "20 req/s"},
        "note": "Profiled against cold instance with no connection reuse -- results unreliable",
    })
    assert r
    assert r.new_step == "1.2 Identify hotspots"
    assert h.step == "1.2 Identify hotspots"

    # Realize profiling was flawed -- go back to re-profile properly
    r = h.back()
    assert r
    assert r.new_step == "1.1 Profile application"
    assert h.step == "1.1 Profile application"
    assert h.status == "running"

    # 1.1 Re-profile with proper warm-up and realistic load
    r = h.submit({
        "tool": "k6 with 2min warm-up + Datadog APM + py-spy",
        "baseline": {"p99": "1.8s", "throughput": "120 req/s", "target_p99": "500ms"},
        "note": "Proper baseline after 2min warm-up with connection pooling enabled",
    })
    assert r
    # 1.2 Identify
    r = h.submit({
        "hotspots": [{"name": "Slow PDF generation", "impact": "1.8s p99 on /invoices/pdf endpoint", "root_cause": "WeasyPrint renders full HTML with external CSS fetch on every request"}],
    })
    assert r
    # 2.1 Analyze
    r = h.submit({
        "hotspot": "Slow PDF generation",
        "analysis": "WeasyPrint fetches 3 external CSS files on each render (200ms). HTML template includes unused sections (400ms parse). No caching of rendered PDFs.",
        "plan": "1) Inline CSS 2) Trim HTML template 3) Cache rendered PDFs in S3 with content-hash key",
    })
    assert r
    # 2.2 Implement
    r = h.submit({
        "change": "Inlined CSS (saves 200ms), trimmed template (saves 250ms), added S3 PDF cache with SHA-256 content hash",
        "p99_after": "380ms (first render), <50ms (cache hit, 92% hit rate)",
    })
    assert r

    # Oops, realize we should have cached before inlining -- back to re-implement
    r = h.back()
    assert r
    assert r.new_step == "2.2 Implement optimization"
    assert h.step == "2.2 Implement optimization"

    # Re-implement with better ordering: cache first, then inline
    r = h.submit({
        "change": "Reordered: S3 cache check first (short-circuit), then inline CSS + trimmed template for cache misses",
        "p99_after": "340ms (miss), <40ms (hit, 94% hit rate after content-hash includes query params)",
    })
    assert r
    # 2.3 Benchmark passes
    r = h.submit_goto("2.0 Hotspot loop")
    assert r
    # 3.1 Final benchmark
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


# ═══════════════════════════════════════════════════════
# Dimension tests: Data accumulation
# ═══════════════════════════════════════════════════════

def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()

    h.submit({"profile": "cpu 80%, mem 60%"})
    data = h.state.data
    assert "1.1 Profile application" in data
    assert data["1.1 Profile application"]["profile"] == "cpu 80%, mem 60%"

    h.submit({"hotspots": ["db_query", "rendering"]})
    data = h.state.data
    assert "1.2 Identify hotspots" in data


def test_s2_data_after_benchmark_retry(harness_factory):
    """Data persists after benchmark retry loop."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    _enter_hotspot_loop(h)

    h.submit({})
    h.submit({"optimization": "v1"})
    h.submit_goto("2.2 Implement optimization")
    h.submit({"optimization": "v2"})
    data = h.state.data
    assert data["2.2 Implement optimization"]["optimization"] == "v2"


# ═══════════════════════════════════════════════════════
# Dimension tests: History audit trail
# ═══════════════════════════════════════════════════════

def test_s1_history_audit_trail(harness_factory):
    """After walkthrough, history contains expected action sequence."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Hotspot loop")
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_s2_history_retry_depth(harness_factory):
    """Multiple benchmark retries produce many history entries."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    _enter_hotspot_loop(h)
    h.submit({})

    for _ in range(4):
        h.submit({})
        h.submit_goto("2.2 Implement optimization")

    history = h.get_history(100)
    assert len(history) >= 15


# ═══════════════════════════════════════════════════════
# Dimension tests: Cross-executor recovery
# ═══════════════════════════════════════════════════════

def test_cross_executor_at_identify(harness_factory):
    """Close at identify step, reopen, state persists."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Identify hotspots"

    h.new_executor()

    assert h.step == "1.2 Identify hotspots"
    assert h.status == "running"


def test_cross_executor_mid_loop(harness_factory):
    """Close mid-loop, reopen, loop state preserved."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1", "h2"]})
    _enter_hotspot_loop(h)

    h.submit({"analysis": "slow query"})
    assert h.step == "2.2 Implement optimization"

    h.new_executor()

    assert h.step == "2.2 Implement optimization"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Hotspot loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    h.goto("3.1 Final benchmark")
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

def test_node_validates_analysis(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    _enter_hotspot_loop(h)

    h.register_node(
        "2.1 Analyze hotspot",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("root_cause") else "must include root_cause",
        ),
    )

    r = h.submit({"notes": "no root cause"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"root_cause": "N+1 query"})
    assert r
    assert r.new_step == "2.2 Implement optimization"


def test_node_validates_profile(harness_factory):
    """Validate node on profiling step."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()

    h.register_node(
        "1.1 Profile application",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("metrics") else "must include metrics",
        ),
    )

    r = h.submit({"description": "no metrics"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"metrics": {"cpu": 80, "mem": 60}})
    assert r


# ═══════════════════════════════════════════════════════
# Dimension tests: Node archival
# ═══════════════════════════════════════════════════════

def test_node_archives_hotspots(harness_factory):
    """Archive node writes each hotspot to SQLite."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1", "h2"]})
    _enter_hotspot_loop(h)

    h.register_node(
        "2.1 Analyze hotspot",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"name": "string", "severity": "string"}},
            archive={"table": "hotspot_analysis"},
        ),
    )

    for _i in range(2):
        h.submit({"name": f"hotspot_{_i}", "severity": "high"})
        h.submit({})
        h.submit_goto("2.0 Hotspot loop")

    rows = h.get_archived_rows("hotspot_analysis")
    assert len(rows) == 2
    assert rows[0]["name"] == "hotspot_0"
    assert rows[1]["name"] == "hotspot_1"


# ═══════════════════════════════════════════════════════
# Dimension tests: Error boundaries
# ═══════════════════════════════════════════════════════

def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    assert h.status == "running"

    r = h.reject("bad")
    assert not r
    assert "not waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    h.goto("3.1 Final benchmark")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    h.goto("3.1 Final benchmark")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_resume_on_running_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ═══════════════════════════════════════════════════════
# Generic / cross-cutting tests
# ═══════════════════════════════════════════════════════

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    h.submit({"profile": "baseline"})

    h.save_checkpoint("at_identify")

    h.submit({})
    assert h.step == "2.1 Analyze hotspot"

    restored = h.load_checkpoint("at_identify")
    assert restored is not None
    assert restored.current_step == "1.2 Identify hotspots"
    assert "1.1 Profile application" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    assert h.step == "1.1 Profile application"

    r = h.retry()
    assert r
    assert h.step == "1.1 Profile application"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step fails."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_back_returns_to_previous(harness_factory):
    """Back returns to the previously visited step."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Identify hotspots"

    r = h.back()
    assert r
    assert h.step == "1.1 Profile application"


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Profile application"


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["a", "b", "c"]})
    _enter_hotspot_loop(h)

    loop_info = h.state.loop_state["2.0 Hotspot loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_hotspot(h)
    h.submit_goto("2.0 Hotspot loop")

    loop_info = h.state.loop_state["2.0 Hotspot loop"]
    assert loop_info["i"] == 1


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["h1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Identify hotspots"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "1.2 Identify hotspots"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"


# ═══════════════════════════════════════════════════════
# Turing machine condition checker tests
# ═══════════════════════════════════════════════════════

def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["N+1 query"]})
    h.start()
    h.register_node(
        "1.1 Profile application",
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
    h = harness_factory("p3-perf-optimization.yaml", loop_data={"hotspots": ["N+1 query"]})
    h.start()
    h.register_node(
        "1.1 Profile application",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
