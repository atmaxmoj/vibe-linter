"""Topic Cluster Pillar Page workflow tests (p5-topic-cluster.yaml).

Tests the pillar + satellite loop pattern with review fallback
to the satellite loop for more content.
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# --- Helpers ---

def _advance_to_satellite_loop(h):
    """Start -> plan -> write pillar -> approve pillar review -> enter satellite loop."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1
    h.submit({})  # 2.1 -> 2.2 (wait)
    assert h.step == "2.2 Pillar review"
    h.approve()
    h.submit_goto("3.0 Satellite loop")
    assert h.step == "3.1 Write satellite article"


def _do_one_satellite(h):
    """At 3.1, complete one satellite (3.1 -> 3.2 -> loop)."""
    h.submit({})  # 3.1 -> 3.2
    h.submit({})  # 3.2 -> loop header


# ===============================================================
# Existing tests (unchanged)
# ===============================================================

def test_1_pillar_5_satellites(harness_factory):
    """Build a 'Docker for DevOps' topic cluster: 1 pillar page + 5 satellite articles targeting long-tail keywords."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1", "s2", "s3", "s4", "s5"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define pillar topic"
    assert h.status == "running"

    r = h.submit({
        "pillar_topic": "Docker for DevOps: Complete Guide",
        "primary_keyword": "docker devops",
        "search_volume": 5400,
        "kd": 52,
        "cluster_goal": "Rank for 'docker devops' and 15+ related long-tail queries",
    })
    assert r
    assert r.new_step == "1.2 Plan satellite articles"
    assert h.step == "1.2 Plan satellite articles"

    r = h.submit({
        "satellites": [
            {"title": "Docker Compose Tutorial", "keyword": "docker compose tutorial", "vol": 8100},
            {"title": "Docker vs Kubernetes", "keyword": "docker vs kubernetes", "vol": 12100},
            {"title": "Dockerfile Best Practices", "keyword": "dockerfile best practices", "vol": 3600},
            {"title": "Docker Multi-Stage Builds", "keyword": "docker multi stage build", "vol": 2400},
            {"title": "Docker Security Hardening", "keyword": "docker security best practices", "vol": 1900},
        ],
        "total_cluster_search_volume": 33500,
    })
    assert r
    assert r.new_step == "2.1 Write pillar page"
    assert h.step == "2.1 Write pillar page"

    r = h.submit({
        "word_count": 5200,
        "h1": "Docker for DevOps: The Complete Guide to Containerization in Production",
        "sections_count": 12,
        "toc": True,
        "schema": "Article",
    })
    assert r
    assert r.new_step == "2.2 Pillar review"
    assert h.step == "2.2 Pillar review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("3.0 Satellite loop")
    assert r
    assert h.step == "3.1 Write satellite article"

    # Write 5 satellites
    satellite_articles = [
        {"title": "Docker Compose Tutorial", "word_count": 3200, "keyword": "docker compose tutorial"},
        {"title": "Docker vs Kubernetes", "word_count": 4100, "keyword": "docker vs kubernetes"},
        {"title": "Dockerfile Best Practices", "word_count": 2800, "keyword": "dockerfile best practices"},
        {"title": "Docker Multi-Stage Builds", "word_count": 2200, "keyword": "docker multi stage build"},
        {"title": "Docker Security Hardening", "word_count": 3500, "keyword": "docker security best practices"},
    ]
    for i in range(5):
        assert h.step == "3.1 Write satellite article"
        r = h.submit(satellite_articles[i])
        assert r
        assert r.new_step == "3.2 Add internal links"
        assert h.step == "3.2 Add internal links"
        r = h.submit({
            "links_to_pillar": 2,
            "links_from_pillar": 1,
            "cross_satellite_links": 1 if i > 0 else 0,
            "anchor_text": "docker devops guide" if i % 2 == 0 else satellite_articles[i]["keyword"],
        })
        assert r
        if i < 4:
            assert h.step == "3.1 Write satellite article"

    assert h.step == "4.1 Internal linking audit"

    r = h.submit({
        "total_internal_links": 23,
        "orphan_pages": 0,
        "pillar_inbound_links": 10,
        "avg_links_per_satellite": 3.6,
        "broken_links": 0,
    })
    assert r
    assert r.new_step == "4.2 Cluster review"
    assert h.step == "4.2 Cluster review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_review_needs_more_satellites(harness_factory):
    """'React hooks' cluster review: missing useRef and useContext articles. Send back to satellite loop."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"pillar_topic": "React Hooks Complete Guide", "primary_keyword": "react hooks", "search_volume": 22200})
    assert r
    r = h.submit({"satellites": [{"title": "useState Guide", "keyword": "react usestate", "vol": 9900}]})
    assert r
    r = h.submit({"word_count": 4800, "h1": "React Hooks: The Definitive Guide (2025)"})
    assert r
    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("3.0 Satellite loop")
    assert r

    # Complete single satellite
    r = h.submit({"title": "useState Guide", "word_count": 2600, "keyword": "react usestate"})
    assert r
    r = h.submit({"links_to_pillar": 3, "anchor_text": "react hooks guide"})
    assert r

    r = h.submit({"total_internal_links": 4, "coverage_gaps": ["useRef", "useContext", "custom hooks"]})
    assert r
    assert h.step == "4.2 Cluster review"
    assert h.status == "waiting"

    # Reviewer: cluster too thin, need useRef, useContext, and custom hooks satellites
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("3.0 Satellite loop")
    assert r
    assert h.step == "3.1 Write satellite article"
    assert h.status == "running"


def test_skip_a_satellite(harness_factory):
    """'Python data science' cluster: skip pandas article (already published last quarter)."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1", "s2", "s3"]},
    )
    r = h.start()
    assert r

    r = h.submit({"pillar_topic": "Python for Data Science", "primary_keyword": "python data science", "search_volume": 14800})
    assert r
    r = h.submit({
        "satellites": [
            {"title": "NumPy Tutorial", "keyword": "numpy tutorial", "vol": 18100},
            {"title": "Pandas Guide", "keyword": "pandas tutorial", "vol": 27100, "note": "already published Q3 2024"},
            {"title": "Matplotlib Visualization", "keyword": "matplotlib tutorial", "vol": 12100},
        ],
    })
    assert r
    r = h.submit({"word_count": 6000, "h1": "Python for Data Science: Complete Learning Path (2025)"})
    assert r
    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("3.0 Satellite loop")
    assert r

    # Satellite 1 (NumPy): complete
    r = h.submit({"title": "NumPy Tutorial for Beginners", "word_count": 3400, "keyword": "numpy tutorial"})
    assert r
    r = h.submit({"links_to_pillar": 2, "links_from_pillar": 1, "anchor_text": "python data science guide"})
    assert r

    # Satellite 2 (Pandas): skip -- already published
    assert h.step == "3.1 Write satellite article"
    r = h.skip("Pandas tutorial already published in Q3 2024 with 12K monthly organic visits")
    assert r
    assert r.new_step == "3.2 Add internal links"
    assert h.step == "3.2 Add internal links"
    r = h.skip("Internal links to pillar already in place from original publication")
    assert r

    # Satellite 3 (Matplotlib): complete
    assert h.step == "3.1 Write satellite article"
    r = h.submit({"title": "Matplotlib Tutorial: Create Publication-Ready Charts", "word_count": 2900, "keyword": "matplotlib tutorial"})
    assert r
    r = h.submit({"links_to_pillar": 2, "links_from_pillar": 1, "cross_satellite_links": 1})
    assert r

    assert h.step == "4.1 Internal linking audit"


def test_empty_satellite_list(harness_factory):
    """'Brand voice guide' cluster: pillar-only content, no satellites needed initially."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": []},
    )
    r = h.start()
    assert r

    r = h.submit({"pillar_topic": "Brand Voice Guide for B2B SaaS", "primary_keyword": "brand voice guide", "search_volume": 2100})
    assert r
    r = h.submit({"satellites": [], "reason": "Pillar-only for now, satellites planned for Q2 after pillar ranks"})
    assert r
    r = h.submit({"word_count": 4500, "h1": "How to Define Your B2B SaaS Brand Voice (With Templates)"})
    assert r
    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("3.0 Satellite loop")
    assert r

    # Loop exits immediately (empty list, transitions[1] = "4.1")
    assert h.step == "4.1 Internal linking audit"
    assert h.status == "running"


def test_stop_then_resume(harness_factory):
    """'Cybersecurity frameworks' pillar page: stop writing to gather NIST 2.0 updates, then resume."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"pillar_topic": "Cybersecurity Frameworks Comparison", "primary_keyword": "cybersecurity frameworks", "search_volume": 6600})
    assert r
    r = h.submit({"satellites": [{"title": "NIST CSF 2.0 Guide", "keyword": "nist csf 2.0", "vol": 3200}]})
    assert r
    assert h.step == "2.1 Write pillar page"

    # Stop to wait for NIST 2.0 final publication to include accurate details
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.1 Write pillar page"

    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.1 Write pillar page"

    r = h.submit({
        "word_count": 5800,
        "h1": "Cybersecurity Frameworks Compared: NIST 2.0, ISO 27001, SOC 2, CIS Controls",
        "frameworks_covered": ["NIST CSF 2.0", "ISO 27001:2022", "SOC 2 Type II", "CIS Controls v8"],
    })
    assert r
    assert r.new_step == "2.2 Pillar review"
    assert h.step == "2.2 Pillar review"


def test_complete_then_reset(harness_factory):
    """Complete 'email deliverability' cluster, reset to start 'email automation' cluster next."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"pillar_topic": "Email Deliverability Guide", "primary_keyword": "email deliverability", "search_volume": 4400})
    assert r
    r = h.submit({"satellites": [{"title": "SPF DKIM DMARC Setup", "keyword": "spf dkim dmarc", "vol": 6600}]})
    assert r
    r = h.submit({"word_count": 4200, "h1": "Email Deliverability: How to Land in the Inbox (2025 Guide)"})
    assert r
    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("3.0 Satellite loop")
    assert r
    r = h.submit({"title": "SPF, DKIM, DMARC Setup Guide", "word_count": 3100, "keyword": "spf dkim dmarc"})
    assert r
    r = h.submit({"links_to_pillar": 3, "anchor_text": "email deliverability guide"})
    assert r
    r = h.submit({"total_internal_links": 6, "orphan_pages": 0})
    assert r
    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define pillar topic"
    assert h.status == "running"


def test_modify_yaml_add_satellite(harness_factory):
    """'GraphQL' cluster: add per-satellite SEO optimization step after realizing satellites rank poorly without it."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"pillar_topic": "GraphQL API Design", "primary_keyword": "graphql api", "search_volume": 8100})
    assert r
    r = h.submit({"satellites": [{"title": "GraphQL Subscriptions Guide", "keyword": "graphql subscriptions", "vol": 2400}]})
    assert r
    r = h.submit({"word_count": 5500, "h1": "GraphQL API Design: From Schema to Production"})
    assert r
    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("3.0 Satellite loop")
    assert r

    r = h.submit({"title": "GraphQL Subscriptions: Real-Time Data Guide", "word_count": 2800, "keyword": "graphql subscriptions"})
    assert r
    assert r.new_step == "3.2 Add internal links"
    assert h.step == "3.2 Add internal links"

    # Realized satellites need dedicated SEO step -- add it via YAML modification
    modified_yaml = """\u540d\u79f0: Topic Cluster Pillar Page
\u63cf\u8ff0: Modified with SEO step in satellite loop

\u6b65\u9aa4:
  - 1.1 Define pillar topic

  - 1.2 Plan satellite articles

  - 2.1 Write pillar page

  - 2.2 Pillar review:
      \u7c7b\u578b: wait
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "pillar page is comprehensive"
          \u53bb: 3.0 Satellite loop
        - \u53bb: 1.1 Define pillar topic

  - 3.0 Satellite loop:
      \u904d\u5386: "satellites"
      \u5b50\u6b65\u9aa4:
        - 3.1 Write satellite article
        - 3.15 Optimize satellite SEO
        - 3.2 Add internal links

  - 4.1 Internal linking audit

  - 4.2 Cluster review:
      \u7c7b\u578b: wait
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "topic cluster is complete"
          \u53bb: Done
        - \u53bb: 3.0 Satellite loop

  - Done:
      \u7c7b\u578b: terminate
"""
    h.reload_yaml(modified_yaml)

    # Test the new step by jumping to it
    r = h.goto("3.15 Optimize satellite SEO")
    assert r
    assert r.new_step == "3.15 Optimize satellite SEO"
    assert h.step == "3.15 Optimize satellite SEO"
    assert h.status == "running"

    r = h.submit({
        "target_keyword": "graphql subscriptions",
        "keyword_in_h1": True,
        "meta_description_optimized": True,
        "schema_markup": "HowTo",
        "image_alt_tags": 3,
    })
    assert r
    assert r.new_step == "3.2 Add internal links"
    assert h.step == "3.2 Add internal links"


def test_goto_internal_linking(harness_factory):
    """'Terraform' cluster: satellites all written, jump straight to linking audit."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    r = h.start()
    assert r

    r = h.goto("4.1 Internal linking audit")
    assert r
    assert r.new_step == "4.1 Internal linking audit"
    assert h.step == "4.1 Internal linking audit"
    assert h.status == "running"

    r = h.submit({
        "total_internal_links": 18,
        "orphan_pages": 1,
        "orphan_details": "Terraform state management article missing link from pillar",
        "broken_links": 0,
        "pillar_inbound": 6,
    })
    assert r
    assert r.new_step == "4.2 Cluster review"
    assert h.step == "4.2 Cluster review"
    assert h.status == "waiting"


def test_back(harness_factory):
    """'API security' cluster: after planning satellites, go back to refine pillar topic scope."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"pillar_topic": "API Security Best Practices", "primary_keyword": "api security", "search_volume": 5400})
    assert r
    assert r.new_step == "1.2 Plan satellite articles"
    assert h.step == "1.2 Plan satellite articles"

    r = h.submit({
        "satellites": [
            {"title": "OAuth 2.0 Guide", "keyword": "oauth 2.0 tutorial", "vol": 9900},
            {"title": "API Rate Limiting", "keyword": "api rate limiting", "vol": 2400},
        ],
        "note": "Realized pillar scope too narrow -- need to include API gateway security",
    })
    assert r
    assert r.new_step == "2.1 Write pillar page"
    assert h.step == "2.1 Write pillar page"

    # Go back to refine satellite plan with broader scope
    r = h.back()
    assert r
    assert r.new_step == "1.2 Plan satellite articles"
    assert h.step == "1.2 Plan satellite articles"


def test_pillar_direction_wrong_back_to_planning(harness_factory):
    """'Machine learning' pillar too broad (targeting 'ML' instead of 'ML for product managers'). Restart topic."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"pillar_topic": "Machine Learning", "primary_keyword": "machine learning", "search_volume": 135000, "kd": 95, "note": "Way too competitive"})
    assert r
    r = h.submit({"satellites": [{"title": "ML Algorithms Overview", "keyword": "machine learning algorithms", "vol": 40500}]})
    assert r
    r = h.submit({"word_count": 6000, "h1": "Machine Learning: Everything You Need to Know", "note": "Too generic, no differentiation"})
    assert r
    assert h.step == "2.2 Pillar review"
    assert h.status == "waiting"

    # Reviewer: topic too broad and competitive, need to niche down to "ML for product managers"
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("1.1 Define pillar topic")
    assert r
    assert r.new_step == "1.1 Define pillar topic"
    assert h.step == "1.1 Define pillar topic"
    assert h.status == "running"

    # Redo with narrower focus
    r = h.submit({
        "pillar_topic": "Machine Learning for Product Managers",
        "primary_keyword": "machine learning for product managers",
        "search_volume": 1600,
        "kd": 28,
        "rationale": "Lower volume but much more targeted, higher conversion potential",
    })
    assert r
    assert r.new_step == "1.2 Plan satellite articles"
    assert h.step == "1.2 Plan satellite articles"


# ===============================================================
# New multi-dimension tests
# ===============================================================

def test_data_accumulates_through_phases(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    h.start()

    h.submit({"pillar_topic": "Machine Learning"})
    data = h.state.data
    assert "1.1 Define pillar topic" in data
    assert data["1.1 Define pillar topic"]["pillar_topic"] == "Machine Learning"

    h.submit({"satellite_plan": ["intro ML", "deep learning", "NLP"]})
    data = h.state.data
    assert "1.2 Plan satellite articles" in data


def test_data_accumulates_in_satellite_loop(harness_factory):
    """Data submitted during satellite loop persists."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1", "s2"]},
    )
    _advance_to_satellite_loop(h)

    h.submit({"article": "Deep Learning Basics"})
    data = h.state.data
    assert "3.1 Write satellite article" in data
    assert data["3.1 Write satellite article"]["article"] == "Deep Learning Basics"


def test_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected actions."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    _advance_to_satellite_loop(h)
    _do_one_satellite(h)
    assert h.step == "4.1 Internal linking audit"
    h.submit({})  # 4.1 -> 4.2
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "approve" in actions
    assert "terminate" in actions[-1]


def test_cross_executor_at_pillar_review(harness_factory):
    """Close executor at pillar review wait, reopen, state persists."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1
    h.submit({})  # 2.1 -> 2.2 (wait)
    assert h.step == "2.2 Pillar review"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "2.2 Pillar review"
    assert h.status == "waiting"


def test_cross_executor_in_satellite_loop(harness_factory):
    """Close executor mid-satellite loop, reopen, loop_state persists."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1", "s2", "s3"]},
    )
    _advance_to_satellite_loop(h)

    _do_one_satellite(h)  # complete satellite 1
    h.submit({})  # 3.1 (satellite 2) -> 3.2
    assert h.step == "3.2 Add internal links"

    h.new_executor()

    assert h.step == "3.2 Add internal links"
    loop_info = h.state.loop_state.get("3.0 Satellite loop")
    assert loop_info is not None
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_node_validates_satellite_article(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    _advance_to_satellite_loop(h)

    h.register_node(
        "3.1 Write satellite article",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("title") else "must include article title",
        ),
    )

    r = h.submit({"notes": "draft"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"title": "Deep Learning for Beginners"})
    assert r
    assert r.new_step == "3.2 Add internal links"


def test_node_archives_satellites(harness_factory):
    """Archive node writes satellite data to SQLite table per iteration."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1", "s2"]},
    )
    _advance_to_satellite_loop(h)

    h.register_node(
        "3.1 Write satellite article",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"title": "string", "topic": "string"}},
            archive={"table": "satellite_articles"},
        ),
    )

    h.submit({"title": "Intro to ML", "topic": "basics"})
    h.submit({})  # 3.2

    h.submit({"title": "Advanced NLP", "topic": "nlp"})

    rows = h.get_archived_rows("satellite_articles")
    assert len(rows) == 2
    assert rows[0]["title"] == "Intro to ML"
    assert rows[1]["title"] == "Advanced NLP"


def test_submit_on_waiting_pillar_review_fails(harness_factory):
    """Submit while pillar review is waiting returns failure."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    assert h.step == "2.2 Pillar review"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    h.start()
    h.submit({"pillar_topic": "AI"})
    h.submit({})
    assert h.step == "2.1 Write pillar page"

    h.save_checkpoint("at_pillar_write")

    h.submit({})
    assert h.step == "2.2 Pillar review"

    restored = h.load_checkpoint("at_pillar_write")
    assert restored is not None
    assert restored.current_step == "2.1 Write pillar page"


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    h.start()
    assert h.step == "1.1 Define pillar topic"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define pillar topic"
    assert h.status == "running"


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    h.start()
    h.submit({})
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )
    _advance_to_satellite_loop(h)
    _do_one_satellite(h)
    h.submit({})  # 4.1 -> 4.2
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p5-topic-cluster.yaml",
        loop_data={"satellites": ["s1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define pillar topic"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p5-topic-cluster.yaml", loop_data={"satellites": ["s1"]})
    h.start()
    h.register_node(
        "1.1 Define pillar topic",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step.\n\n## Steps\n1. Analyze\n2. Implement",
            check=lambda data: True,
        ),
    )
    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory("p5-topic-cluster.yaml", loop_data={"satellites": ["s1"]})
    h.start()
    h.register_node(
        "1.1 Define pillar topic",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
