"""Skyscraper Technique workflow tests (p5-skyscraper.yaml).

Tests the quality comparison 2-way branching, outreach loop,
and the track response 2-way (both go back to loop).
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# --- Helpers ---

def _advance_to_outreach_loop(h):
    """Start -> benchmark -> analyze -> write -> quality passes -> enter outreach loop."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1
    h.submit({})  # 2.1 -> 2.2
    h.submit_goto("3.0 Outreach loop")  # quality passes
    assert h.step == "3.1 Contact target"


def _do_one_outreach(h):
    """At 3.1, complete one outreach cycle (3.1 -> 3.2 -> loop)."""
    h.submit({})  # 3.1 -> 3.2
    h.submit_goto("3.0 Outreach loop")  # 3.2 -> loop header


# ===============================================================
# Existing tests (unchanged)
# ===============================================================

def test_content_better_outreach_5_targets(harness_factory):
    """Skyscraper campaign for 'remote work statistics 2025' -- outperform Owl Labs report, outreach to 5 sites."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1", "t2", "t3", "t4", "t5"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Find benchmark content"
    assert h.status == "running"

    r = h.submit({
        "benchmark_url": "https://owllabs.com/blog/remote-work-statistics",
        "benchmark_title": "Remote Work Statistics 2024 (Owl Labs)",
        "referring_domains": 1240,
        "keyword": "remote work statistics",
        "search_volume": 8100,
        "benchmark_word_count": 2800,
    })
    assert r
    assert r.new_step == "1.2 Analyze benchmark"
    assert h.step == "1.2 Analyze benchmark"

    r = h.submit({
        "strengths": ["Strong brand authority", "Original survey data from 2K+ respondents", "Clean infographics"],
        "weaknesses": ["Data only from US", "No industry breakdown", "Missing remote work productivity metrics", "No citations to academic studies"],
        "improvement_plan": "Add global data (EU/APAC), industry-specific stats, productivity studies, interactive charts",
    })
    assert r
    assert r.new_step == "2.1 Write superior content"
    assert h.step == "2.1 Write superior content"

    r = h.submit({
        "title": "150+ Remote Work Statistics for 2025 (Global Data, By Industry)",
        "word_count": 6200,
        "unique_stats": 156,
        "original_data_points": 23,
        "infographics": 8,
        "sources_cited": 45,
    })
    assert r
    assert r.new_step == "2.2 Quality comparison"
    assert h.step == "2.2 Quality comparison"

    # Content clearly beats benchmark
    r = h.submit_goto("3.0 Outreach loop")
    assert r
    assert h.step == "3.1 Contact target"

    # Contact 5 targets that link to the Owl Labs benchmark
    outreach_targets = [
        {"site": "buffer.com", "contact": "editorial@buffer.com", "context": "Their State of Remote Work links to Owl Labs"},
        {"site": "hubspot.com/blog", "contact": "blog-team@hubspot.com", "context": "Remote work roundup post"},
        {"site": "forbes.com", "contact": "contributor DM", "context": "Forbes remote work column"},
        {"site": "zapier.com/blog", "contact": "wade@zapier.com", "context": "Remote work resources page"},
        {"site": "flexjobs.com", "contact": "press@flexjobs.com", "context": "Remote work statistics roundup"},
    ]
    for i in range(5):
        assert h.step == "3.1 Contact target"
        r = h.submit(outreach_targets[i])
        assert r
        assert r.new_step == "3.2 Track response"
        assert h.step == "3.2 Track response"
        r = h.submit_goto("3.0 Outreach loop")
        assert r
        if i < 4:
            assert h.step == "3.1 Contact target"

    assert h.step == "4.1 Analyze outreach results"

    r = h.submit({
        "total_outreach": 5,
        "responses_received": 5,
        "backlinks_secured": 5,
        "response_rate": "100%",
        "estimated_dr_impact": "+3 points",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_quality_not_enough_keep_improving(harness_factory):
    """'SaaS pricing page examples' skyscraper: first two drafts don't beat benchmark. Third attempt adds original screenshots."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "benchmark_url": "https://www.priceintelligently.com/blog/saas-pricing-page-examples",
        "referring_domains": 380,
        "benchmark_word_count": 3500,
        "benchmark_examples": 12,
    })
    assert r
    r = h.submit({
        "weaknesses": ["Only 12 examples", "No conversion rate data", "Screenshots from 2022 (outdated)"],
        "improvement_plan": "30+ examples with current screenshots, pricing psychology annotations, A/B test data",
    })
    assert r
    r = h.submit({
        "title": "25 Best SaaS Pricing Pages (2025)",
        "word_count": 4200,
        "examples": 25,
        "note": "Only 25 examples vs planned 30, no A/B test data yet",
    })
    assert r
    assert h.step == "2.2 Quality comparison"

    # Not good enough -- only 25 examples, missing A/B data
    r = h.submit_goto("2.1 Write superior content")
    assert r
    assert r.new_step == "2.1 Write superior content"
    assert h.step == "2.1 Write superior content"

    r = h.submit({
        "title": "35 Best SaaS Pricing Pages with Conversion Data (2025)",
        "word_count": 5800,
        "examples": 35,
        "note": "Added 10 more examples but still no original screenshots",
    })
    assert r
    assert r.new_step == "2.2 Quality comparison"
    assert h.step == "2.2 Quality comparison"

    # Still not clearly better -- missing original visual analysis
    r = h.submit_goto("2.1 Write superior content")
    assert r
    assert h.step == "2.1 Write superior content"

    r = h.submit({
        "title": "35 Best SaaS Pricing Pages: Annotated Screenshots + Conversion Data (2025)",
        "word_count": 7200,
        "examples": 35,
        "original_screenshots": 35,
        "pricing_psychology_annotations": 35,
        "ab_test_data_points": 8,
    })
    assert r
    assert h.step == "2.2 Quality comparison"

    # Now clearly superior
    r = h.submit_goto("3.0 Outreach loop")
    assert r
    assert h.step == "3.1 Contact target"


def test_all_outreach_rejected(harness_factory):
    """'JavaScript framework comparison' skyscraper: all 3 outreach targets decline. Analyze and move on."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1", "t2", "t3"]},
    )
    r = h.start()
    assert r

    r = h.submit({"benchmark_url": "https://stateofjs.com/frameworks", "referring_domains": 890, "keyword": "javascript frameworks comparison"})
    assert r
    r = h.submit({"weaknesses": ["Survey-only data", "No performance benchmarks", "Annual updates only"]})
    assert r
    r = h.submit({"title": "JavaScript Frameworks 2025: Performance Benchmarks + Developer Survey", "word_count": 8500})
    assert r
    r = h.submit_goto("3.0 Outreach loop")
    assert r

    # All 3 targets decline (both branches go to loop)
    rejections = [
        {"site": "smashingmagazine.com", "contact": "editors@smashing.com", "email_subject": "Updated JS framework data for your resources page"},
        {"site": "css-tricks.com", "contact": "guest-posts@css-tricks.com", "email_subject": "Better JS framework comparison than State of JS"},
        {"site": "dev.to", "contact": "partnerships@dev.to", "email_subject": "Original benchmark data for JS frameworks"},
    ]
    for i in range(3):
        assert h.step == "3.1 Contact target"
        r = h.submit(rejections[i])
        assert r
        assert r.new_step == "3.2 Track response"
        assert h.step == "3.2 Track response"
        r = h.submit_goto("3.0 Outreach loop")
        assert r
        if i < 2:
            assert h.step == "3.1 Contact target"

    assert h.step == "4.1 Analyze outreach results"

    r = h.submit({
        "total_outreach": 3,
        "responses_received": 2,
        "backlinks_secured": 0,
        "response_rate": "67%",
        "success_rate": "0%",
        "lessons_learned": "State of JS has strong editorial partnerships; try targeting individual blogger sites instead",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_skip_an_outreach_target(harness_factory):
    """'Email marketing ROI' skyscraper: skip HubSpot outreach (competitor), contact the other two."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1", "t2", "t3"]},
    )
    r = h.start()
    assert r

    r = h.submit({"benchmark_url": "https://litmus.com/blog/email-marketing-roi", "referring_domains": 520, "keyword": "email marketing roi"})
    assert r
    r = h.submit({"weaknesses": ["No 2025 data", "US-only", "Missing e-commerce vertical breakdown"]})
    assert r
    r = h.submit({"title": "Email Marketing ROI in 2025: Data by Industry, Company Size, and Region", "word_count": 5400})
    assert r
    r = h.submit_goto("3.0 Outreach loop")
    assert r

    # Target 1 (Mailchimp blog): complete
    r = h.submit({"site": "mailchimp.com/resources", "contact": "content@mailchimp.com", "pitch": "Updated ROI data with e-commerce breakdown"})
    assert r
    r = h.submit_goto("3.0 Outreach loop")
    assert r

    # Target 2 (HubSpot): skip -- they are a competitor to our client
    assert h.step == "3.1 Contact target"
    r = h.skip("HubSpot is a direct competitor to our client -- skip outreach to avoid promoting competitor content")
    assert r
    assert r.new_step == "3.2 Track response"
    assert h.step == "3.2 Track response"
    r = h.submit_goto("3.0 Outreach loop")
    assert r

    # Target 3 (Campaign Monitor blog): complete
    assert h.step == "3.1 Contact target"
    r = h.submit({"site": "campaignmonitor.com/blog", "contact": "editorial@cm.com", "pitch": "Original ROI benchmarks by industry vertical"})
    assert r
    r = h.submit_goto("3.0 Outreach loop")
    assert r

    assert h.step == "4.1 Analyze outreach results"


def test_stop_then_resume(harness_factory):
    """'Technical SEO checklist' skyscraper: stop writing to verify Core Web Vitals data, then resume."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "benchmark_url": "https://ahrefs.com/blog/technical-seo-checklist",
        "referring_domains": 670,
        "keyword": "technical seo checklist",
    })
    assert r
    r = h.submit({
        "weaknesses": ["No interactive checklist", "Missing Core Web Vitals section", "No tool screenshots"],
    })
    assert r
    assert h.step == "2.1 Write superior content"

    # Stop to verify latest Core Web Vitals thresholds from web.dev before writing
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.1 Write superior content"

    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.1 Write superior content"

    r = h.submit({
        "title": "The Ultimate Technical SEO Checklist (2025): 87 Points with Tool Screenshots",
        "word_count": 9200,
        "checklist_items": 87,
        "interactive_checklist": True,
        "core_web_vitals_section": True,
        "tool_screenshots": 24,
    })
    assert r
    assert r.new_step == "2.2 Quality comparison"
    assert h.step == "2.2 Quality comparison"


def test_complete_then_reset(harness_factory):
    """Complete 'link building strategies' skyscraper, reset for next campaign targeting 'content marketing statistics'."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"benchmark_url": "https://backlinko.com/link-building", "referring_domains": 2100, "keyword": "link building strategies"})
    assert r
    r = h.submit({"weaknesses": ["Published 2023", "No video walkthroughs", "Missing AI-powered link building tools"]})
    assert r
    r = h.submit({"title": "Link Building in 2025: 21 Strategies with Step-by-Step Walkthroughs", "word_count": 8800})
    assert r
    r = h.submit_goto("3.0 Outreach loop")
    assert r
    r = h.submit({"site": "searchenginejournal.com", "contact": "editorial@sej.com"})
    assert r
    r = h.submit_goto("3.0 Outreach loop")
    assert r
    r = h.submit({"total_outreach": 1, "backlinks_secured": 1, "response_rate": "100%"})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Find benchmark content"
    assert h.status == "running"


def test_empty_outreach_list(harness_factory):
    """'API documentation best practices' skyscraper: content-only play, no outreach targets (organic link bait)."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": []},
    )
    r = h.start()
    assert r

    r = h.submit({"benchmark_url": "https://swagger.io/resources/api-documentation-best-practices/", "referring_domains": 310})
    assert r
    r = h.submit({"weaknesses": ["No real-world examples", "Missing OpenAPI 3.1 guidance", "No interactive playground"]})
    assert r
    r = h.submit({"title": "API Documentation Best Practices: 50+ Examples from Top Developer Platforms", "word_count": 7500})
    assert r
    r = h.submit_goto("3.0 Outreach loop")
    assert r

    # Loop exits immediately (no outreach targets -- relying on organic link acquisition)
    assert h.step == "4.1 Analyze outreach results"
    assert h.status == "running"


def test_back(harness_factory):
    """'Conversion rate optimization' skyscraper: go back to re-analyze benchmark after finding additional competitor."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "benchmark_url": "https://www.crazyegg.com/blog/conversion-rate-optimization/",
        "referring_domains": 450,
        "keyword": "conversion rate optimization guide",
    })
    assert r
    assert r.new_step == "1.2 Analyze benchmark"
    assert h.step == "1.2 Analyze benchmark"

    r = h.submit({
        "weaknesses": ["No A/B testing examples", "Missing mobile CRO section"],
        "note": "Discovered Unbounce has a stronger competing page -- need to re-analyze",
    })
    assert r
    assert r.new_step == "2.1 Write superior content"
    assert h.step == "2.1 Write superior content"

    # Go back to add Unbounce as a second benchmark to beat
    r = h.back()
    assert r
    assert r.new_step == "1.2 Analyze benchmark"
    assert h.step == "1.2 Analyze benchmark"


def test_goto(harness_factory):
    """'B2B lead generation' skyscraper: content already written offline, jump to outreach phase.

    goto() sets current_step but doesn't trigger loop handling.
    A submit from the loop header then enters the first child.
    """
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    r = h.start()
    assert r

    r = h.goto("3.0 Outreach loop")
    assert r
    assert r.new_step == "3.0 Outreach loop"
    assert h.step == "3.0 Outreach loop"
    assert h.status == "running"

    # Submit from the loop header enters the first child
    r = h.submit({"note": "Content already written offline: 'B2B Lead Generation: 40 Tactics for 2025'"})
    assert r
    assert r.new_step == "3.1 Contact target"
    assert h.step == "3.1 Contact target"


def test_modify_yaml(harness_factory):
    """'Content marketing tools' skyscraper: add social media promotion step after outreach phase completes."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"benchmark_url": "https://contentmarketinginstitute.com/tools/", "referring_domains": 580, "keyword": "content marketing tools"})
    assert r
    r = h.submit({"weaknesses": ["No pricing comparison", "Missing AI tools category", "Not updated for 2025"]})
    assert r
    r = h.submit({"title": "67 Content Marketing Tools Compared (2025): Pricing, Ratings, and Real User Reviews", "word_count": 10200})
    assert r
    r = h.submit_goto("3.0 Outreach loop")
    assert r
    r = h.submit({"site": "contentmarketinginstitute.com", "contact": "joe@cmi.com", "pitch": "Updated resource with 67 tools including AI category"})
    assert r
    r = h.submit_goto("3.0 Outreach loop")
    assert r

    assert h.step == "4.1 Analyze outreach results"

    # Add social promotion step
    modified_yaml = """\u540d\u79f0: Skyscraper Technique
\u63cf\u8ff0: Modified with promotion step

\u6b65\u9aa4:
  - 1.1 Find benchmark content

  - 1.2 Analyze benchmark

  - 2.1 Write superior content

  - 2.2 Quality comparison:
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "content is clearly better than benchmark"
          \u53bb: 3.0 Outreach loop
        - \u53bb: 2.1 Write superior content

  - 3.0 Outreach loop:
      \u904d\u5386: "outreach_targets"
      \u5b50\u6b65\u9aa4:
        - 3.1 Contact target
        - 3.2 Track response:
            \u4e0b\u4e00\u6b65:
              - \u5982\u679c: "got a positive response or backlink"
                \u53bb: 3.0 Outreach loop
              - \u53bb: 3.0 Outreach loop

  - 4.1 Analyze outreach results

  - 4.2 Promote on social media

  - Done:
      \u7c7b\u578b: terminate
"""
    h.reload_yaml(modified_yaml)

    r = h.submit({"total_outreach": 1, "backlinks_secured": 1})
    assert r
    assert r.new_step == "4.2 Promote on social media"
    assert h.step == "4.2 Promote on social media"

    r = h.submit({
        "platforms": ["Twitter/X", "LinkedIn", "Reddit r/contentmarketing"],
        "posts_scheduled": 6,
        "threads_created": 2,
        "influencer_tags": ["@joepulizzi", "@randfish"],
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# New multi-dimension tests
# ===============================================================

def test_data_accumulates_through_phases(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    h.start()

    h.submit({"benchmark_url": "https://example.com/best-article"})
    data = h.state.data
    assert "1.1 Find benchmark content" in data
    assert data["1.1 Find benchmark content"]["benchmark_url"] == "https://example.com/best-article"

    h.submit({"gaps": ["missing section", "outdated stats"]})
    data = h.state.data
    assert "1.2 Analyze benchmark" in data


def test_data_accumulates_in_outreach_loop(harness_factory):
    """Data submitted during outreach loop persists."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1", "t2"]},
    )
    _advance_to_outreach_loop(h)

    h.submit({"email": "sent to t1"})
    data = h.state.data
    assert "3.1 Contact target" in data
    assert data["3.1 Contact target"]["email"] == "sent to t1"


def test_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected actions."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    _advance_to_outreach_loop(h)
    _do_one_outreach(h)
    assert h.step == "4.1 Analyze outreach results"
    h.submit({})  # 4.1 -> Done
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_cross_executor_at_quality_comparison(harness_factory):
    """Close executor at quality comparison, reopen, state persists."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1
    h.submit({})  # 2.1 -> 2.2
    assert h.step == "2.2 Quality comparison"

    h.new_executor()

    assert h.step == "2.2 Quality comparison"
    assert h.status == "running"


def test_cross_executor_in_outreach_loop(harness_factory):
    """Close executor mid-outreach loop, reopen, loop_state persists."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1", "t2", "t3"]},
    )
    _advance_to_outreach_loop(h)

    _do_one_outreach(h)  # complete target 1
    h.submit({})  # 3.1 (target 2) -> 3.2
    assert h.step == "3.2 Track response"

    h.new_executor()

    assert h.step == "3.2 Track response"
    loop_info = h.state.loop_state.get("3.0 Outreach loop")
    assert loop_info is not None
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_node_validates_contact(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    _advance_to_outreach_loop(h)

    h.register_node(
        "3.1 Contact target",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("email_sent") else "must confirm email sent",
        ),
    )

    r = h.submit({"notes": "thinking about it"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"email_sent": True})
    assert r
    assert r.new_step == "3.2 Track response"


def test_node_archives_outreach_results(harness_factory):
    """Archive node writes outreach data to SQLite table per iteration."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1", "t2"]},
    )
    _advance_to_outreach_loop(h)

    h.register_node(
        "3.1 Contact target",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"target": "string", "method": "string"}},
            archive={"table": "outreach_log"},
        ),
    )

    h.submit({"target": "t1", "method": "email"})
    h.submit_goto("3.0 Outreach loop")

    h.submit({"target": "t2", "method": "linkedin"})

    rows = h.get_archived_rows("outreach_log")
    assert len(rows) == 2
    assert rows[0]["target"] == "t1"
    assert rows[1]["method"] == "linkedin"


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure (no wait steps in skyscraper)."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    h.start()
    h.submit({"benchmark": "article X"})
    h.submit({})
    assert h.step == "2.1 Write superior content"

    h.save_checkpoint("at_writing")

    h.submit({})
    assert h.step == "2.2 Quality comparison"

    restored = h.load_checkpoint("at_writing")
    assert restored is not None
    assert restored.current_step == "2.1 Write superior content"


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    h.start()
    h.submit({})  # 1.1 -> 1.2
    assert h.step == "1.2 Analyze benchmark"

    r = h.retry()
    assert r
    assert h.step == "1.2 Analyze benchmark"
    assert h.status == "running"


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
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
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )
    _advance_to_outreach_loop(h)
    _do_one_outreach(h)
    h.submit({})  # 4.1 -> Done
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p5-skyscraper.yaml",
        loop_data={"outreach_targets": ["t1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Find benchmark content"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p5-skyscraper.yaml", loop_data={"outreach_targets": ["t1"]})
    h.start()
    h.register_node(
        "1.1 Find benchmark content",
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
    h = harness_factory("p5-skyscraper.yaml", loop_data={"outreach_targets": ["t1"]})
    h.start()
    h.register_node(
        "1.1 Find benchmark content",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
