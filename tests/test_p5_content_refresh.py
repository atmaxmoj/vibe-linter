"""Content Refresh workflow tests (p5-content-refresh.yaml).

Tests the article loop with quality check 2-way branching,
fully autonomous flow with no wait steps.
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# --- Helpers ---

def _advance_to_article_loop(h):
    """Start -> submit 1.1, 1.2 -> arrive at 2.1 Analyze article performance."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (enters article loop)
    assert h.step == "2.1 Analyze article performance"


def _do_one_article(h):
    """At 2.1, complete one article cycle (2.1 -> 2.2 -> 2.3 -> 2.4 -> loop)."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit({})  # 2.3 -> 2.4
    h.submit_goto("2.0 Article loop")  # 2.4 -> loop header


# ===============================================================
# Existing tests (unchanged)
# ===============================================================

def test_update_8_articles(harness_factory):
    """Refresh 8 blog articles from a B2B SaaS site -- update outdated stats, fix broken links, improve SEO."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": [f"a{i}" for i in range(1, 9)]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Audit existing content"
    assert h.status == "running"

    r = h.submit({
        "total_articles_audited": 142,
        "articles_needing_refresh": 38,
        "criteria": ["Published > 12 months ago", "Position dropped 5+ spots", "Broken links detected", "CTR below 2%"],
        "tool": "Google Search Console + Screaming Frog",
    })
    assert r
    assert r.new_step == "1.2 Prioritize articles"
    assert h.step == "1.2 Prioritize articles"

    r = h.submit({
        "priority_method": "Score = (monthly organic traffic) * (position drop magnitude) * (conversion rate)",
        "top_8": [
            {"url": "/blog/crm-comparison", "traffic": 8200, "position_drop": 7},
            {"url": "/blog/email-automation-guide", "traffic": 6100, "position_drop": 12},
            {"url": "/blog/saas-pricing-strategies", "traffic": 5800, "position_drop": 4},
            {"url": "/blog/customer-onboarding", "traffic": 4900, "position_drop": 9},
            {"url": "/blog/lead-scoring-models", "traffic": 4200, "position_drop": 6},
            {"url": "/blog/sales-pipeline-management", "traffic": 3800, "position_drop": 11},
            {"url": "/blog/churn-reduction-tactics", "traffic": 3500, "position_drop": 8},
            {"url": "/blog/product-led-growth", "traffic": 3100, "position_drop": 5},
        ],
    })
    assert r
    assert r.new_step == "2.1 Analyze article performance"
    assert h.step == "2.1 Analyze article performance"

    # Update 8 articles, all pass quality check first try
    articles_data = [
        {"url": "/blog/crm-comparison", "current_position": 14, "target_position": 5, "broken_links": 3, "outdated_stats": 8},
        {"url": "/blog/email-automation-guide", "current_position": 18, "target_position": 6, "broken_links": 1, "outdated_stats": 5},
        {"url": "/blog/saas-pricing-strategies", "current_position": 11, "target_position": 5, "broken_links": 0, "outdated_stats": 12},
        {"url": "/blog/customer-onboarding", "current_position": 16, "target_position": 7, "broken_links": 2, "outdated_stats": 4},
        {"url": "/blog/lead-scoring-models", "current_position": 13, "target_position": 5, "broken_links": 1, "outdated_stats": 6},
        {"url": "/blog/sales-pipeline-management", "current_position": 19, "target_position": 8, "broken_links": 4, "outdated_stats": 9},
        {"url": "/blog/churn-reduction-tactics", "current_position": 15, "target_position": 7, "broken_links": 2, "outdated_stats": 7},
        {"url": "/blog/product-led-growth", "current_position": 12, "target_position": 5, "broken_links": 0, "outdated_stats": 3},
    ]
    for i in range(8):
        assert h.step == "2.1 Analyze article performance"
        r = h.submit(articles_data[i])
        assert r
        assert r.new_step == "2.2 Update content"
        assert h.step == "2.2 Update content"
        r = h.submit({"stats_updated": articles_data[i]["outdated_stats"], "links_fixed": articles_data[i]["broken_links"], "sections_rewritten": 2})
        assert r
        assert r.new_step == "2.3 Optimize SEO"
        assert h.step == "2.3 Optimize SEO"
        r = h.submit({"title_tag_updated": True, "meta_description_rewritten": True, "internal_links_added": 3, "schema_added": "FAQPage"})
        assert r
        assert r.new_step == "2.4 Quality check"
        assert h.step == "2.4 Quality check"
        r = h.submit_goto("2.0 Article loop")
        assert r
        if i < 7:
            assert h.step == "2.1 Analyze article performance"

    assert h.step == "3.1 Publish updates"

    r = h.submit({
        "articles_published": 8,
        "total_stats_updated": sum(a["outdated_stats"] for a in articles_data),
        "total_links_fixed": sum(a["broken_links"] for a in articles_data),
        "reindex_requested": True,
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_skip_one_article(harness_factory):
    """3-article refresh: skip the 'company culture' post (only 50 monthly visits, not worth the effort)."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1", "a2", "a3"]},
    )
    r = h.start()
    assert r

    r = h.submit({"total_articles_audited": 85, "articles_needing_refresh": 12})
    assert r
    r = h.submit({"top_3": ["/blog/crm-features-guide", "/blog/company-culture-tips", "/blog/sales-forecasting"]})
    assert r

    # Article 1 (CRM features): complete
    r = h.submit({"url": "/blog/crm-features-guide", "monthly_traffic": 4200, "position": 12, "broken_links": 2})
    assert r
    r = h.submit({"sections_rewritten": 3, "stats_updated": 5, "new_screenshots": 4})
    assert r
    r = h.submit({"title_updated": True, "meta_desc_updated": True, "internal_links_added": 2})
    assert r
    r = h.submit_goto("2.0 Article loop")
    assert r

    # Article 2 (company culture): only 50 visits/mo, skip it
    assert h.step == "2.1 Analyze article performance"
    r = h.skip("Only 50 monthly visits, no commercial intent, not worth refreshing")
    assert r
    assert r.new_step == "2.2 Update content"
    assert h.step == "2.2 Update content"
    r = h.skip("Skipping -- article deprioritized")
    assert r
    assert r.new_step == "2.3 Optimize SEO"
    assert h.step == "2.3 Optimize SEO"
    r = h.skip("Skipping -- article deprioritized")
    assert r
    assert r.new_step == "2.4 Quality check"
    assert h.step == "2.4 Quality check"
    r = h.submit_goto("2.0 Article loop")
    assert r

    # Article 3 (sales forecasting): complete
    assert h.step == "2.1 Analyze article performance"
    r = h.submit({"url": "/blog/sales-forecasting", "monthly_traffic": 3800, "position": 15, "broken_links": 1})
    assert r
    r = h.submit({"sections_rewritten": 2, "stats_updated": 8, "added_calculator_embed": True})
    assert r
    r = h.submit({"title_updated": True, "schema_added": "HowTo", "internal_links_added": 3})
    assert r
    r = h.submit_goto("2.0 Article loop")
    assert r

    assert h.step == "3.1 Publish updates"


def test_seo_strategy_changes_stop_modify_resume(harness_factory):
    """Google algorithm update mid-refresh: stop, add keyword re-targeting step via YAML, resume."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1", "a2"]},
    )
    r = h.start()
    assert r

    r = h.submit({"total_articles_audited": 60, "articles_needing_refresh": 8, "audit_tool": "Ahrefs Content Audit"})
    assert r
    r = h.submit({"top_2": ["/blog/lead-generation-strategies", "/blog/ab-testing-guide"]})
    assert r

    # Start first article
    r = h.submit({"url": "/blog/lead-generation-strategies", "monthly_traffic": 5200, "position": 11})
    assert r
    r = h.submit({"sections_rewritten": 4, "stats_updated": 6, "new_examples": 3})
    assert r
    assert h.step == "2.3 Optimize SEO"

    # Google March 2025 core update dropped -- need to add keyword re-targeting step
    r = h.stop()
    assert r
    assert h.status == "stopped"

    modified_yaml = """\u540d\u79f0: Content Refresh
\u63cf\u8ff0: Modified with keyword update

\u6b65\u9aa4:
  - 1.1 Audit existing content

  - 1.2 Prioritize articles

  - 2.0 Article loop:
      \u904d\u5386: "articles"
      \u5b50\u6b65\u9aa4:
        - 2.1 Analyze article performance
        - 2.2 Update content
        - 2.25 Update target keywords
        - 2.3 Optimize SEO
        - 2.4 Quality check:
            \u4e0b\u4e00\u6b65:
              - \u5982\u679c: "article meets current standards"
                \u53bb: 2.0 Article loop
              - \u53bb: 2.2 Update content

  - 3.1 Publish updates

  - Done:
      \u7c7b\u578b: terminate
"""
    h.reload_yaml(modified_yaml)
    r = h.resume()
    assert r
    assert h.status == "running"

    # Continue from where we stopped (2.3 Optimize SEO)
    r = h.submit({"title_updated": True, "meta_desc_updated": True, "post_core_update_adjustments": "Added E-E-A-T signals, author byline, updated date"})
    assert r
    assert r.new_step == "2.4 Quality check"
    assert h.step == "2.4 Quality check"


def test_complete_then_reset(harness_factory):
    """Complete Q1 content refresh batch, reset for Q2 batch."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"total_articles_audited": 45, "quarter": "Q1 2025"})
    assert r
    r = h.submit({"top_1": ["/blog/remote-hiring-guide"]})
    assert r
    r = h.submit({"url": "/blog/remote-hiring-guide", "monthly_traffic": 3200, "position": 14, "age_months": 18})
    assert r
    r = h.submit({"sections_rewritten": 5, "stats_updated": 9, "before_word_count": 2100, "after_word_count": 3400})
    assert r
    r = h.submit({"title_updated": True, "target_keyword_refreshed": "remote hiring guide 2025", "schema_added": "HowTo"})
    assert r
    r = h.submit_goto("2.0 Article loop")
    assert r
    r = h.submit({"articles_published": 1, "reindex_requested": True})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Audit existing content"
    assert h.status == "running"


def test_empty_article_list(harness_factory):
    """Content audit reveals all articles are fresh (published within 6 months) -- nothing to refresh."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": []},
    )
    r = h.start()
    assert r

    r = h.submit({"total_articles_audited": 32, "articles_needing_refresh": 0, "reason": "All articles published within last 6 months"})
    assert r
    r = h.submit({"priority_list": [], "note": "No articles meet refresh criteria -- all content is fresh"})
    assert r

    # Loop exits immediately
    assert h.step == "3.1 Publish updates"
    assert h.status == "running"


def test_back(harness_factory):
    """After prioritizing, go back to re-audit after discovering Screaming Frog missed JS-rendered pages."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"total_articles_audited": 80, "tool": "Screaming Frog", "note": "Static crawl only"})
    assert r
    assert r.new_step == "1.2 Prioritize articles"
    assert h.step == "1.2 Prioritize articles"

    # Realized audit missed JS-rendered pages -- go back
    r = h.back()
    assert r
    assert r.new_step == "1.1 Audit existing content"
    assert h.step == "1.1 Audit existing content"

    r = h.submit({"total_articles_audited": 112, "tool": "Screaming Frog + JS rendering mode", "note": "Found 32 additional JS-rendered pages"})
    assert r
    assert r.new_step == "1.2 Prioritize articles"
    assert h.step == "1.2 Prioritize articles"


def test_article_keeps_failing_retry(harness_factory):
    """'Email deliverability guide' article fails quality 4 times (thin content, bad readability, no examples, missing schema)."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"total_articles_audited": 40, "articles_needing_refresh": 5})
    assert r
    r = h.submit({"top_1": ["/blog/email-deliverability-guide"]})
    assert r

    # Fail quality check 4 times with different issues each time
    for _attempt in range(4):
        r = h.submit({"url": "/blog/email-deliverability-guide", "monthly_traffic": 2800, "position": 18})
        assert r
        r = h.submit({"sections_rewritten": _attempt + 1, "word_count_added": 400 * (_attempt + 1)})
        assert r
        r = h.submit({"title_updated": True, "internal_links_added": _attempt + 1})
        assert r
        assert h.step == "2.4 Quality check"
        r = h.submit_goto("2.2 Update content")
        assert r
        assert r.new_step == "2.2 Update content"
        assert h.step == "2.2 Update content"

    # 5th attempt: passes all quality criteria
    r = h.submit({
        "sections_rewritten": 8,
        "word_count_added": 2200,
        "case_studies": 4,
        "before_after_metrics": True,
    })
    assert r
    r = h.submit({"schema_added": "FAQPage", "featured_snippet_optimized": True, "flesch_kincaid": 9})
    assert r
    assert h.step == "2.4 Quality check"
    r = h.submit_goto("2.0 Article loop")
    assert r

    assert h.step == "3.1 Publish updates"


def test_goto_publish(harness_factory):
    """All articles already updated offline via bulk CMS import -- jump to publish step."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    r = h.start()
    assert r

    r = h.goto("3.1 Publish updates")
    assert r
    assert r.new_step == "3.1 Publish updates"
    assert h.step == "3.1 Publish updates"
    assert h.status == "running"

    r = h.submit({
        "articles_published": 12,
        "method": "Bulk CMS import via WordPress REST API",
        "reindex_requested": True,
        "sitemap_updated": True,
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_stop(harness_factory):
    """Stop mid-article update when content team needs to review brand voice guidelines before continuing."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"total_articles_audited": 25, "articles_needing_refresh": 3})
    assert r
    r = h.submit({"top_1": ["/blog/saas-onboarding-best-practices"]})
    assert r
    r = h.submit({"url": "/blog/saas-onboarding-best-practices", "monthly_traffic": 2100, "position": 17, "broken_links": 1})
    assert r
    assert h.step == "2.2 Update content"

    # Stop -- content team needs to review updated brand voice guidelines before rewriting
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Update content"


def test_goto_invalid_step(harness_factory):
    """Attempt to goto a removed step name returns error."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    r = h.start()
    assert r

    r = h.goto("99.9 Archive old articles")
    assert not r
    assert "not found" in r.message.lower()
    assert h.step == "1.1 Audit existing content"


# ===============================================================
# New multi-dimension tests
# ===============================================================

def test_data_accumulates_through_phases(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    h.start()

    h.submit({"total_articles": 50, "outdated": 12})
    data = h.state.data
    assert "1.1 Audit existing content" in data
    assert data["1.1 Audit existing content"]["total_articles"] == 50

    h.submit({"priority_list": ["a1", "a5", "a10"]})
    data = h.state.data
    assert "1.2 Prioritize articles" in data


def test_data_accumulates_in_article_loop(harness_factory):
    """Data submitted during article loop persists."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1", "a2"]},
    )
    _advance_to_article_loop(h)

    h.submit({"pageviews": 1200, "bounce_rate": 0.65})
    data = h.state.data
    assert "2.1 Analyze article performance" in data
    assert data["2.1 Analyze article performance"]["pageviews"] == 1200


def test_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected actions."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    _advance_to_article_loop(h)
    _do_one_article(h)
    assert h.step == "3.1 Publish updates"
    h.submit({})  # 3.1 -> Done
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_cross_executor_in_article_loop(harness_factory):
    """Close executor mid-article loop, reopen, loop_state persists."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1", "a2", "a3"]},
    )
    _advance_to_article_loop(h)

    _do_one_article(h)  # complete article 1
    h.submit({})  # 2.1 (article 2) -> 2.2
    assert h.step == "2.2 Update content"

    h.new_executor()

    assert h.step == "2.2 Update content"
    loop_info = h.state.loop_state.get("2.0 Article loop")
    assert loop_info is not None
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_cross_executor_at_publish(harness_factory):
    """Close executor at publish step, reopen, state persists."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    _advance_to_article_loop(h)
    _do_one_article(h)
    assert h.step == "3.1 Publish updates"

    h.new_executor()

    assert h.step == "3.1 Publish updates"
    assert h.status == "running"


def test_node_validates_article_analysis(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    _advance_to_article_loop(h)

    h.register_node(
        "2.1 Analyze article performance",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("metrics") else "must include performance metrics",
        ),
    )

    r = h.submit({"notes": "looks ok"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"metrics": {"pageviews": 500}})
    assert r
    assert r.new_step == "2.2 Update content"


def test_node_archives_article_updates(harness_factory):
    """Archive node writes article update data to SQLite per iteration."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1", "a2"]},
    )
    _advance_to_article_loop(h)

    h.register_node(
        "2.2 Update content",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"article_id": "string", "changes": "string"}},
            archive={"table": "article_updates"},
        ),
    )

    # Article 1
    h.submit({})  # 2.1 -> 2.2
    h.submit({"article_id": "a1", "changes": "updated stats"})
    h.submit({})  # 2.3 -> 2.4
    h.submit_goto("2.0 Article loop")

    # Article 2
    h.submit({})  # 2.1 -> 2.2
    h.submit({"article_id": "a2", "changes": "added section"})

    rows = h.get_archived_rows("article_updates")
    assert len(rows) == 2
    assert rows[0]["article_id"] == "a1"
    assert rows[1]["article_id"] == "a2"


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure (no wait steps in content refresh)."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    _advance_to_article_loop(h)

    h.save_checkpoint("at_article_loop")

    _do_one_article(h)
    assert h.step == "3.1 Publish updates"

    restored = h.load_checkpoint("at_article_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Analyze article performance"


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    h.start()
    h.submit({})  # 1.1 -> 1.2
    assert h.step == "1.2 Prioritize articles"

    r = h.retry()
    assert r
    assert h.step == "1.2 Prioritize articles"
    assert h.status == "running"


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
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
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )
    h.start()
    h.goto("3.1 Publish updates")
    h.submit({})
    assert h.step == "Done"
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p5-content-refresh.yaml",
        loop_data={"articles": ["a1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Audit existing content"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p5-content-refresh.yaml", loop_data={"articles": ["a1"]})
    h.start()
    h.register_node(
        "1.1 Audit existing content",
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
    h = harness_factory("p5-content-refresh.yaml", loop_data={"articles": ["a1"]})
    h.start()
    h.register_node(
        "1.1 Audit existing content",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
