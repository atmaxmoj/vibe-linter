"""Content Gap Analysis workflow tests (p5-content-gap.yaml).

Tests the gap loop with ranking check 2-way branching,
where failing ranking sends back to content creation.
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# --- Helpers ---

def _advance_to_gap_loop(h):
    """Start -> submit 1.1, 1.2 -> arrive at 2.1 Create content for gap."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (enters gap loop)
    assert h.step == "2.1 Create content for gap"


def _do_one_gap(h):
    """At 2.1, complete one gap cycle (2.1 -> 2.2 -> 2.3 -> loop)."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit_goto("2.0 Gap loop")  # 2.3 -> loop header


# ===============================================================
# Existing tests (unchanged)
# ===============================================================

def test_fill_5_gaps(harness_factory):
    """Fill 5 keyword gaps found in Ahrefs Content Gap analysis vs HubSpot, Salesforce, and Pipedrive."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1", "g2", "g3", "g4", "g5"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Analyze competitor content"
    assert h.status == "running"

    r = h.submit({
        "competitors": ["hubspot.com/blog", "salesforce.com/resources", "pipedrive.com/blog"],
        "tool": "Ahrefs Content Gap",
        "our_domain": "ourcrm.io/blog",
        "competitor_keywords_total": 4200,
        "our_keywords_total": 1800,
        "gap_keywords": 2400,
    })
    assert r
    assert r.new_step == "1.2 Identify content gaps"
    assert h.step == "1.2 Identify content gaps"

    r = h.submit({
        "gaps_identified": 5,
        "gap_list": [
            {"keyword": "sales pipeline stages", "vol": 6600, "kd": 38, "competitors_ranking": ["HubSpot #2", "Pipedrive #5"]},
            {"keyword": "crm data migration", "vol": 2400, "kd": 28, "competitors_ranking": ["Salesforce #3"]},
            {"keyword": "sales forecasting methods", "vol": 3600, "kd": 42, "competitors_ranking": ["HubSpot #4", "Salesforce #7"]},
            {"keyword": "customer success metrics", "vol": 4400, "kd": 35, "competitors_ranking": ["HubSpot #1"]},
            {"keyword": "lead qualification frameworks", "vol": 2900, "kd": 31, "competitors_ranking": ["Pipedrive #3"]},
        ],
        "total_gap_search_volume": 19900,
    })
    assert r
    assert r.new_step == "2.1 Create content for gap"
    assert h.step == "2.1 Create content for gap"

    # Fill 5 gaps, all rank well first try
    gap_articles = [
        {"title": "7 Sales Pipeline Stages: Complete Guide with Templates", "word_count": 3800, "keyword": "sales pipeline stages"},
        {"title": "CRM Data Migration: Step-by-Step Guide (No Data Loss)", "word_count": 2900, "keyword": "crm data migration"},
        {"title": "Sales Forecasting Methods: 5 Models Compared with Examples", "word_count": 4200, "keyword": "sales forecasting methods"},
        {"title": "12 Customer Success Metrics Every SaaS Company Should Track", "word_count": 3500, "keyword": "customer success metrics"},
        {"title": "Lead Qualification Frameworks: BANT, MEDDIC, CHAMP Compared", "word_count": 3100, "keyword": "lead qualification frameworks"},
    ]
    seo_optimizations = [
        {"target_keyword": "sales pipeline stages", "keyword_in_h1": True, "meta_desc": True, "schema": "HowTo", "internal_links": 4},
        {"target_keyword": "crm data migration", "keyword_in_h1": True, "meta_desc": True, "schema": "HowTo", "internal_links": 3},
        {"target_keyword": "sales forecasting methods", "keyword_in_h1": True, "meta_desc": True, "schema": "Article", "internal_links": 5},
        {"target_keyword": "customer success metrics", "keyword_in_h1": True, "meta_desc": True, "schema": "Article", "internal_links": 4},
        {"target_keyword": "lead qualification frameworks", "keyword_in_h1": True, "meta_desc": True, "schema": "Article", "internal_links": 3},
    ]
    for i in range(5):
        assert h.step == "2.1 Create content for gap"
        r = h.submit(gap_articles[i])
        assert r
        assert r.new_step == "2.2 Optimize for target keyword"
        assert h.step == "2.2 Optimize for target keyword"
        r = h.submit(seo_optimizations[i])
        assert r
        assert r.new_step == "2.3 Ranking check"
        assert h.step == "2.3 Ranking check"
        r = h.submit_goto("2.0 Gap loop")
        assert r
        if i < 4:
            assert h.step == "2.1 Create content for gap"

    assert h.step == "3.1 Overall ranking review"

    r = h.submit({
        "gaps_filled": 5,
        "articles_published": 5,
        "total_new_keywords_ranking": 23,
        "avg_initial_position": 8.4,
        "estimated_monthly_traffic_gain": 3200,
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_ranking_not_enough_edit_content(harness_factory):
    """'CRM integration guide' ranks at position 22 (target: top 10). Rewrite twice before hitting position 7."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"competitors": ["zapier.com/blog", "hubspot.com/blog"], "tool": "Ahrefs Content Gap"})
    assert r
    r = h.submit({"gaps_identified": 1, "gap_list": [{"keyword": "crm integration guide", "vol": 3200, "kd": 44}]})
    assert r

    # First attempt: ranks at position 22 (too low)
    r = h.submit({"title": "CRM Integration Guide", "word_count": 2100, "keyword": "crm integration guide"})
    assert r
    r = h.submit({"target_keyword": "crm integration guide", "keyword_in_h1": True, "meta_desc": True})
    assert r
    assert h.step == "2.3 Ranking check"
    r = h.submit_goto("2.1 Create content for gap")
    assert r
    assert r.new_step == "2.1 Create content for gap"
    assert h.step == "2.1 Create content for gap"

    # Second attempt: ranks at position 14 (better but still below target)
    r = h.submit({"title": "CRM Integration Guide: 15 Popular Integrations Explained", "word_count": 3800, "keyword": "crm integration guide", "added": "integration screenshots, step-by-step walkthroughs"})
    assert r
    r = h.submit({"target_keyword": "crm integration guide", "schema_added": "HowTo", "faq_schema": True})
    assert r
    assert h.step == "2.3 Ranking check"
    r = h.submit_goto("2.1 Create content for gap")
    assert r
    assert h.step == "2.1 Create content for gap"

    # Third attempt: ranks at position 7 (within target)
    r = h.submit({"title": "CRM Integration Guide: Connect Your CRM to 30+ Tools (2025)", "word_count": 5200, "keyword": "crm integration guide", "added": "video tutorials, downloadable integration checklist, expert quotes"})
    assert r
    r = h.submit({"target_keyword": "crm integration guide", "video_embed": True, "downloadable_pdf": True, "expert_quotes": 3})
    assert r
    r = h.submit_goto("2.0 Gap loop")
    assert r
    assert h.step == "3.1 Overall ranking review"


def test_skip_low_priority_gap(harness_factory):
    """3 gaps identified, skip 'CRM glossary' (low search volume, informational-only intent)."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1", "g2", "g3"]},
    )
    r = h.start()
    assert r

    r = h.submit({"competitors": ["hubspot.com", "pipedrive.com"], "tool": "Ahrefs"})
    assert r
    r = h.submit({
        "gaps_identified": 3,
        "gap_list": [
            {"keyword": "sales email templates", "vol": 5400, "kd": 35},
            {"keyword": "crm glossary", "vol": 320, "kd": 12, "note": "Low volume, informational only"},
            {"keyword": "deal pipeline automation", "vol": 2800, "kd": 40},
        ],
    })
    assert r

    # Gap 1 (sales email templates): complete
    r = h.submit({"title": "25 Sales Email Templates That Get Replies (2025)", "word_count": 4100, "keyword": "sales email templates"})
    assert r
    r = h.submit({"target_keyword": "sales email templates", "keyword_in_h1": True, "meta_desc": True})
    assert r
    r = h.submit_goto("2.0 Gap loop")
    assert r

    # Gap 2 (CRM glossary): skip -- only 320 monthly searches, no commercial intent
    assert h.step == "2.1 Create content for gap"
    r = h.skip("Only 320 monthly searches, purely informational intent, no conversion potential")
    assert r
    assert r.new_step == "2.2 Optimize for target keyword"
    assert h.step == "2.2 Optimize for target keyword"
    r = h.skip("Skipping optimization for deprioritized gap")
    assert r
    assert r.new_step == "2.3 Ranking check"
    assert h.step == "2.3 Ranking check"
    r = h.submit_goto("2.0 Gap loop")
    assert r

    # Gap 3 (deal pipeline automation): complete
    assert h.step == "2.1 Create content for gap"
    r = h.submit({"title": "Deal Pipeline Automation: Save 10hrs/Week with These Workflows", "word_count": 3200, "keyword": "deal pipeline automation"})
    assert r
    r = h.submit({"target_keyword": "deal pipeline automation", "keyword_in_h1": True, "schema": "HowTo"})
    assert r
    r = h.submit_goto("2.0 Gap loop")
    assert r

    assert h.step == "3.1 Overall ranking review"


def test_empty_gap_list(harness_factory):
    """Content gap analysis reveals no gaps -- our site already covers all competitor keywords."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": []},
    )
    r = h.start()
    assert r

    r = h.submit({
        "competitors": ["competitor-a.com", "competitor-b.com"],
        "tool": "Ahrefs Content Gap",
        "our_keywords": 3200,
        "competitor_keywords": 2800,
        "note": "We already rank for all keywords competitors rank for",
    })
    assert r
    r = h.submit({"gaps_identified": 0, "reason": "Full keyword coverage -- no content gaps found"})
    assert r

    # Loop exits immediately
    assert h.step == "3.1 Overall ranking review"
    assert h.status == "running"


def test_stop_then_resume(harness_factory):
    """'Sales automation' gap article: stop during keyword optimization to wait for Semrush data export."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"competitors": ["hubspot.com", "salesforce.com"], "tool": "Semrush Keyword Gap"})
    assert r
    r = h.submit({"gaps_identified": 1, "gap_list": [{"keyword": "sales automation tools", "vol": 4400, "kd": 48}]})
    assert r
    r = h.submit({"title": "11 Best Sales Automation Tools for Growing Teams (2025)", "word_count": 3600, "keyword": "sales automation tools"})
    assert r
    assert h.step == "2.2 Optimize for target keyword"

    # Stop to wait for Semrush data export with SERP feature opportunities
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Optimize for target keyword"

    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Optimize for target keyword"

    r = h.submit({
        "target_keyword": "sales automation tools",
        "serp_features_targeted": ["Featured snippet", "People Also Ask", "Video carousel"],
        "keyword_in_h1": True,
        "faq_schema": True,
    })
    assert r
    assert r.new_step == "2.3 Ranking check"
    assert h.step == "2.3 Ranking check"


def test_complete_then_reset(harness_factory):
    """Complete gap analysis vs HubSpot/Pipedrive, reset to analyze vs Freshsales/Zoho next."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"competitors": ["hubspot.com", "pipedrive.com"], "tool": "Ahrefs Content Gap"})
    assert r
    r = h.submit({"gaps_identified": 1, "gap_list": [{"keyword": "sales playbook template", "vol": 2400, "kd": 32}]})
    assert r
    r = h.submit({"title": "Sales Playbook Template: Free Download + 12 Examples", "word_count": 3200, "keyword": "sales playbook template"})
    assert r
    r = h.submit({"target_keyword": "sales playbook template", "keyword_in_h1": True, "downloadable_template": True})
    assert r
    r = h.submit_goto("2.0 Gap loop")
    assert r
    r = h.submit({"gaps_filled": 1, "new_keywords_ranking": 4, "estimated_traffic_gain": 680})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Analyze competitor content"
    assert h.status == "running"


def test_competitor_changed_modify_yaml(harness_factory):
    """New competitor (Freshsales) enters market mid-analysis. Add re-analysis step to incorporate their content."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "competitors": ["hubspot.com", "pipedrive.com"],
        "tool": "Ahrefs Content Gap",
        "note": "Freshsales just launched 40 new blog posts -- need to add them to analysis",
    })
    assert r
    assert r.new_step == "1.2 Identify content gaps"
    assert h.step == "1.2 Identify content gaps"

    # Add re-analysis step for the new competitor
    modified_yaml = """\u540d\u79f0: Content Gap Analysis
\u63cf\u8ff0: Modified with re-analysis step

\u6b65\u9aa4:
  - 1.1 Analyze competitor content

  - 1.15 Re-analyze new competitor:
      \u4e0b\u4e00\u6b65: 1.2 Identify content gaps

  - 1.2 Identify content gaps

  - 2.0 Gap loop:
      \u904d\u5386: "gaps"
      \u5b50\u6b65\u9aa4:
        - 2.1 Create content for gap
        - 2.2 Optimize for target keyword
        - 2.3 Ranking check:
            \u4e0b\u4e00\u6b65:
              - \u5982\u679c: "ranking meets target position"
                \u53bb: 2.0 Gap loop
              - \u53bb: 2.1 Create content for gap

  - 3.1 Overall ranking review

  - Done:
      \u7c7b\u578b: terminate
"""
    h.reload_yaml(modified_yaml)

    r = h.goto("1.15 Re-analyze new competitor")
    assert r
    assert r.new_step == "1.15 Re-analyze new competitor"
    assert h.step == "1.15 Re-analyze new competitor"
    assert h.status == "running"

    r = h.submit({
        "new_competitor": "freshsales.io/blog",
        "new_keywords_discovered": 85,
        "additional_gaps": 3,
        "note": "Freshsales ranks for 85 keywords we don't cover",
    })
    assert r
    assert r.new_step == "1.2 Identify content gaps"
    assert h.step == "1.2 Identify content gaps"


def test_goto(harness_factory):
    """All gap content already published -- jump to ranking review to check positions."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    r = h.start()
    assert r

    r = h.goto("3.1 Overall ranking review")
    assert r
    assert r.new_step == "3.1 Overall ranking review"
    assert h.step == "3.1 Overall ranking review"
    assert h.status == "running"

    r = h.submit({
        "gaps_filled": 8,
        "articles_ranking_top_10": 5,
        "articles_ranking_11_20": 2,
        "articles_not_indexed": 1,
        "total_traffic_gain": 4800,
        "top_performer": {"keyword": "sales pipeline stages", "position": 3, "traffic": 1200},
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_back(harness_factory):
    """After identifying gaps, go back to add a missed competitor (Zendesk Sell) to the analysis."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "competitors": ["hubspot.com", "pipedrive.com"],
        "tool": "Ahrefs Content Gap",
        "note": "Forgot to include Zendesk Sell -- they launched 20 new pages last month",
    })
    assert r
    assert r.new_step == "1.2 Identify content gaps"
    assert h.step == "1.2 Identify content gaps"

    # Go back to add Zendesk Sell to competitor analysis
    r = h.back()
    assert r
    assert r.new_step == "1.1 Analyze competitor content"
    assert h.step == "1.1 Analyze competitor content"

    r = h.submit({
        "competitors": ["hubspot.com", "pipedrive.com", "zendesk.com/sell"],
        "tool": "Ahrefs Content Gap",
        "additional_keywords_from_zendesk": 45,
    })
    assert r
    assert r.new_step == "1.2 Identify content gaps"
    assert h.step == "1.2 Identify content gaps"


def test_modify_yaml_delete_current_step(harness_factory):
    """Mid-gap work, realize keyword optimization step is redundant (merged into content creation). Stop and reset."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"competitors": ["hubspot.com", "salesforce.com"], "tool": "Semrush"})
    assert r
    r = h.submit({"gaps_identified": 1, "gap_list": [{"keyword": "customer retention strategies", "vol": 5400, "kd": 45}]})
    assert r
    r = h.submit({"title": "15 Customer Retention Strategies for SaaS Companies", "word_count": 3800})
    assert r
    assert h.step == "2.2 Optimize for target keyword"

    # Realize keyword optimization is redundant -- writer already handles SEO during creation
    r = h.stop()
    assert r
    assert h.status == "stopped"

    # Reset to start with revised workflow
    h.reset()
    assert h.state is None

    # Start fresh with new workflow plan
    r = h.start()
    assert r
    assert h.step == "1.1 Analyze competitor content"
    assert h.status == "running"


# ===============================================================
# New multi-dimension tests
# ===============================================================

def test_data_accumulates_through_phases(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    h.start()

    h.submit({"competitors_analyzed": 5})
    data = h.state.data
    assert "1.1 Analyze competitor content" in data
    assert data["1.1 Analyze competitor content"]["competitors_analyzed"] == 5

    h.submit({"gaps_found": 3})
    data = h.state.data
    assert "1.2 Identify content gaps" in data
    assert data["1.2 Identify content gaps"]["gaps_found"] == 3


def test_data_accumulates_in_gap_loop(harness_factory):
    """Data submitted during gap loop persists."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1", "g2"]},
    )
    _advance_to_gap_loop(h)

    h.submit({"content": "New article about gap g1"})
    data = h.state.data
    assert "2.1 Create content for gap" in data
    assert data["2.1 Create content for gap"]["content"] == "New article about gap g1"


def test_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected actions."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    _advance_to_gap_loop(h)
    _do_one_gap(h)
    assert h.step == "3.1 Overall ranking review"
    h.submit({})  # 3.1 -> Done
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_cross_executor_in_gap_loop(harness_factory):
    """Close executor mid-gap loop, reopen, loop_state persists."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1", "g2", "g3"]},
    )
    _advance_to_gap_loop(h)

    _do_one_gap(h)  # complete gap 1
    h.submit({})  # 2.1 (gap 2) -> 2.2
    assert h.step == "2.2 Optimize for target keyword"

    h.new_executor()

    assert h.step == "2.2 Optimize for target keyword"
    loop_info = h.state.loop_state.get("2.0 Gap loop")
    assert loop_info is not None
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_cross_executor_at_ranking_review(harness_factory):
    """Close executor at ranking review, reopen, state persists."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    _advance_to_gap_loop(h)
    _do_one_gap(h)
    assert h.step == "3.1 Overall ranking review"

    h.new_executor()

    assert h.step == "3.1 Overall ranking review"
    assert h.status == "running"


def test_node_validates_gap_content(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    _advance_to_gap_loop(h)

    h.register_node(
        "2.1 Create content for gap",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("article") else "must include article content",
        ),
    )

    r = h.submit({"notes": "thinking about it"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"article": "Complete guide to keyword X"})
    assert r
    assert r.new_step == "2.2 Optimize for target keyword"


def test_node_archives_gap_data(harness_factory):
    """Archive node writes gap data to SQLite table per iteration."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1", "g2"]},
    )
    _advance_to_gap_loop(h)

    h.register_node(
        "2.1 Create content for gap",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"gap_id": "string", "keyword": "string"}},
            archive={"table": "gap_content"},
        ),
    )

    h.submit({"gap_id": "g1", "keyword": "python tutorial"})
    h.submit({})  # 2.2
    h.submit_goto("2.0 Gap loop")  # 2.3

    h.submit({"gap_id": "g2", "keyword": "rust guide"})

    rows = h.get_archived_rows("gap_content")
    assert len(rows) == 2
    assert rows[0]["gap_id"] == "g1"
    assert rows[1]["keyword"] == "rust guide"


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure (no wait steps in content gap)."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    _advance_to_gap_loop(h)

    h.save_checkpoint("at_gap_loop")

    _do_one_gap(h)
    assert h.step == "3.1 Overall ranking review"

    restored = h.load_checkpoint("at_gap_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Create content for gap"


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    h.start()
    h.submit({})  # 1.1 -> 1.2
    assert h.step == "1.2 Identify content gaps"

    r = h.retry()
    assert r
    assert h.step == "1.2 Identify content gaps"
    assert h.status == "running"


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
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
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )
    h.start()
    h.goto("3.1 Overall ranking review")
    h.submit({})
    assert h.step == "Done"
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p5-content-gap.yaml",
        loop_data={"gaps": ["g1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Analyze competitor content"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p5-content-gap.yaml", loop_data={"gaps": ["g1"]})
    h.start()
    h.register_node(
        "1.1 Analyze competitor content",
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
    h = harness_factory("p5-content-gap.yaml", loop_data={"gaps": ["g1"]})
    h.start()
    h.register_node(
        "1.1 Analyze competitor content",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
