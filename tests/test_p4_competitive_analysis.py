"""Competitive Analysis workflow tests (p4-competitive-analysis.yaml).

Tests the competitor loop, comparison matrix, and review wait
with fallback to the competitor loop for more research.
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, EditPolicyPattern, NodeDefinition

# --- Helpers ---

def _advance_to_competitor_loop(h):
    """Start -> submit 1.1, 1.2 -> arrive at 2.1 Research competitor."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (enters competitor loop)
    assert h.step == "2.1 Research competitor"


def _do_one_competitor(h):
    """At 2.1, complete one competitor cycle (2.1 -> 2.2 -> 2.3 -> loop/next)."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit({})  # 2.3 -> loop header


# ===============================================================
# Existing tests (unchanged)
# ===============================================================

def test_analyze_5_competitors(harness_factory):
    """Analyze 5 project management SaaS competitors for a Series A startup entering the market."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1", "c2", "c3", "c4", "c5"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define analysis criteria"
    assert h.status == "running"

    r = h.submit({
        "criteria": ["pricing_model", "feature_depth", "integrations", "market_share", "NPS_score", "enterprise_readiness"],
        "market": "Project Management SaaS for mid-market (50-500 employees)",
        "our_positioning": "AI-native project management with predictive resource allocation",
    })
    assert r
    assert r.new_step == "1.2 Identify competitors"
    assert h.step == "1.2 Identify competitors"

    r = h.submit({
        "competitors": [
            {"name": "Asana", "tier": "Leader", "estimated_revenue": "$550M ARR"},
            {"name": "Monday.com", "tier": "Leader", "estimated_revenue": "$730M ARR"},
            {"name": "ClickUp", "tier": "Challenger", "estimated_revenue": "$200M ARR"},
            {"name": "Linear", "tier": "Niche", "estimated_revenue": "$50M ARR"},
            {"name": "Notion Projects", "tier": "Emerging", "estimated_revenue": "Part of $900M Notion ARR"},
        ],
        "selection_method": "G2 Grid leaders + emerging players with AI features",
    })
    assert r
    assert r.new_step == "2.1 Research competitor"
    assert h.step == "2.1 Research competitor"

    competitor_data = [
        {"name": "Asana", "founded": 2008, "employees": 1800, "funding": "$450M", "key_customers": ["Deloitte", "NASA", "Spotify"]},
        {"name": "Monday.com", "founded": 2012, "employees": 1900, "funding": "Public (MNDY)", "key_customers": ["Coca-Cola", "Canva", "BBC"]},
        {"name": "ClickUp", "founded": 2017, "employees": 1000, "funding": "$537M", "key_customers": ["Samsung", "Booking.com", "IBM"]},
        {"name": "Linear", "founded": 2019, "employees": 80, "funding": "$52M", "key_customers": ["Vercel", "Ramp", "Retool"]},
        {"name": "Notion Projects", "founded": 2013, "employees": 800, "funding": "$343M", "key_customers": ["Figma", "Nike", "Toyota"]},
    ]
    strengths_weaknesses = [
        {"strengths": ["Strong enterprise features", "Robust API", "Brand recognition"], "weaknesses": ["Bloated UI", "Expensive at scale", "Slow AI adoption"]},
        {"strengths": ["Visual flexibility", "No-code automations", "Strong marketing"], "weaknesses": ["Performance issues with large datasets", "Limited developer workflows"]},
        {"strengths": ["All-in-one platform", "Aggressive pricing", "Fast feature shipping"], "weaknesses": ["Feature bloat", "UX inconsistency", "Reliability concerns"]},
        {"strengths": ["Developer-first UX", "Speed and performance", "Opinionated workflow"], "weaknesses": ["Limited to engineering teams", "No resource management", "Small ecosystem"]},
        {"strengths": ["Flexible knowledge base", "Beautiful design", "Strong community"], "weaknesses": ["Project features immature", "No Gantt charts", "Weak reporting"]},
    ]
    findings = [
        {"market_position": "Incumbent leader, defending share", "pricing": "$10.99-24.99/user/mo", "ai_features": "AI teammate (basic)"},
        {"market_position": "Fastest growing, strong SMB", "pricing": "$8-19/user/mo", "ai_features": "AI column suggestions"},
        {"market_position": "Aggressive disruptor", "pricing": "Free-$12/user/mo", "ai_features": "ClickUp Brain (GPT integration)"},
        {"market_position": "Dev-team darling", "pricing": "$8/user/mo flat", "ai_features": "AI issue writing, triage"},
        {"market_position": "Horizontal platform expanding into PM", "pricing": "$8-15/user/mo", "ai_features": "Notion AI (writing assistant)"},
    ]

    # Loop through 5 competitors
    for i in range(5):
        assert h.step == "2.1 Research competitor"
        r = h.submit(competitor_data[i])
        assert r
        assert r.new_step == "2.2 Analyze strengths and weaknesses"
        assert h.step == "2.2 Analyze strengths and weaknesses"
        r = h.submit(strengths_weaknesses[i])
        assert r
        assert r.new_step == "2.3 Document findings"
        assert h.step == "2.3 Document findings"
        r = h.submit(findings[i])
        assert r
        if i < 4:
            assert h.step == "2.1 Research competitor"

    assert h.step == "3.1 Create comparison matrix"

    r = h.submit({
        "matrix_dimensions": ["Pricing", "AI Features", "Enterprise Readiness", "Integrations", "UX Quality", "Performance"],
        "scoring_scale": "1-5",
        "our_gaps": ["Brand awareness", "Integration ecosystem"],
        "our_advantages": ["AI-native architecture", "Predictive analytics", "Modern tech stack"],
    })
    assert r
    assert r.new_step == "3.2 Generate insights"
    assert h.step == "3.2 Generate insights"

    r = h.submit({
        "key_insights": [
            "No competitor has true predictive resource allocation -- clear differentiator",
            "Market moving from 'PM tool' to 'AI work OS' -- we are positioned for this shift",
            "Linear proves developer-first UX wins loyalty -- apply to broader audience",
            "Pricing sweet spot is $8-15/user/mo for mid-market adoption",
        ],
        "recommended_positioning": "AI-native project intelligence platform",
        "go_to_market": "Target engineering-led mid-market companies frustrated with legacy PM tools",
    })
    assert r
    assert r.new_step == "3.3 Review"
    assert h.step == "3.3 Review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("3.4 Write final report")
    assert r
    assert r.new_step == "3.4 Write final report"
    assert h.step == "3.4 Write final report"

    r = h.submit({
        "report_title": "Competitive Landscape: AI-Native Project Management SaaS",
        "pages": 24,
        "executive_summary": "Market is ripe for AI-native disruption; incumbents are retrofitting AI onto legacy architectures",
        "deliverables": ["Comparison matrix", "Feature gap analysis", "Pricing strategy recommendation", "GTM playbook"],
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_missed_competitor_stop_modify_resume(harness_factory):
    """CRM market analysis: missed HubSpot, stop to add market position step to YAML, resume."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1", "c2"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "criteria": ["CRM features", "pricing", "SMB fit", "API quality"],
        "market": "CRM for SMB SaaS companies",
    })
    assert r
    r = h.submit({
        "competitors": [
            {"name": "Salesforce Essentials", "tier": "Enterprise downsell"},
            {"name": "Pipedrive", "tier": "SMB specialist"},
        ],
    })
    assert r

    # Complete first competitor (Salesforce Essentials)
    r = h.submit({"name": "Salesforce Essentials", "founded": 1999, "employees": 79000})
    assert r
    r = h.submit({"strengths": ["Ecosystem", "Brand"], "weaknesses": ["Complexity", "Cost"]})
    assert r
    r = h.submit({"pricing": "$25/user/mo", "smb_fit_score": "3/10"})
    assert r
    assert h.step == "2.1 Research competitor"

    r = h.stop()
    assert r
    assert h.status == "stopped"

    modified_yaml = """\u540d\u79f0: Competitive Analysis
\u63cf\u8ff0: Modified with extra analysis step

\u6b65\u9aa4:
  - 1.1 Define analysis criteria

  - 1.2 Identify competitors

  - 2.0 Competitor loop:
      \u904d\u5386: "competitors"
      \u5b50\u6b65\u9aa4:
        - 2.1 Research competitor
        - 2.2 Analyze strengths and weaknesses
        - 2.25 Analyze market position
        - 2.3 Document findings

  - 3.1 Create comparison matrix

  - 3.2 Generate insights

  - 3.3 Review:
      \u7c7b\u578b: wait
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "analysis is comprehensive"
          \u53bb: 3.4 Write final report
        - \u53bb: 2.0 Competitor loop

  - 3.4 Write final report

  - Done:
      \u7c7b\u578b: terminate
"""
    h.reload_yaml(modified_yaml)
    r = h.resume()
    assert r
    assert h.status == "running"

    # Continue with second competitor on modified flow
    r = h.submit({})
    assert r
    assert r.new_step == "2.2 Analyze strengths and weaknesses"
    assert h.step == "2.2 Analyze strengths and weaknesses"


def test_review_needs_more_back_to_loop(harness_factory):
    """E-commerce platform analysis incomplete: reviewer says missing Shopify's recent B2B pivot data."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"criteria": ["B2B features", "headless commerce", "pricing", "developer experience"]})
    assert r
    r = h.submit({"competitors": [{"name": "Shopify", "note": "Analyzing B2B expansion"}]})
    assert r

    # Complete the loop
    r = h.submit({"name": "Shopify", "founded": 2006, "market_cap": "$100B+"})
    assert r
    r = h.submit({"strengths": ["Brand", "App ecosystem"], "weaknesses": ["B2B features nascent"]})
    assert r
    r = h.submit({"pricing": "$29-399/mo base", "b2b_features": "Shopify B2B launched 2023"})
    assert r

    r = h.submit({
        "matrix": {"Shopify": {"b2b_score": 4, "developer_experience": 8, "headless": 7}},
    })
    assert r
    r = h.submit({
        "insights": ["Shopify B2B still immature vs BigCommerce", "Missing data on Shopify Markets Pro adoption"],
        "gap": "Need deeper analysis of Shopify's wholesale channel pricing and enterprise case studies",
    })
    assert r
    assert h.step == "3.3 Review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("2.0 Competitor loop")
    assert r
    assert h.step == "2.1 Research competitor"
    assert h.status == "running"


def test_skip_a_competitor(harness_factory):
    """Cloud infrastructure analysis: skip AWS (already analyzed last quarter), focus on GCP and Azure."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1", "c2", "c3"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "criteria": ["Kubernetes support", "AI/ML services", "pricing transparency", "multi-region coverage"],
    })
    assert r
    r = h.submit({
        "competitors": [
            {"name": "Google Cloud Platform"},
            {"name": "AWS", "note": "Analyzed in Q3 report"},
            {"name": "Microsoft Azure"},
        ],
    })
    assert r

    # Competitor 1 (GCP): complete normally
    r = h.submit({"name": "GCP", "market_share": "11%", "key_differentiator": "AI/ML and BigQuery"})
    assert r
    r = h.submit({"strengths": ["Best-in-class Kubernetes (GKE)", "BigQuery", "Competitive pricing"], "weaknesses": ["Smaller enterprise sales team", "Fewer regions"]})
    assert r
    r = h.submit({"pricing_model": "Per-second billing, sustained-use discounts", "kubernetes_score": "9/10"})
    assert r

    # Competitor 2 (AWS): skip -- analyzed thoroughly last quarter
    assert h.step == "2.1 Research competitor"
    r = h.skip("Already know this competitor well")
    assert r
    assert r.new_step == "2.2 Analyze strengths and weaknesses"
    assert h.step == "2.2 Analyze strengths and weaknesses"
    r = h.skip("Known")
    assert r
    assert r.new_step == "2.3 Document findings"
    assert h.step == "2.3 Document findings"
    r = h.skip("Documented elsewhere")
    assert r

    # Competitor 3 (Azure): complete normally
    assert h.step == "2.1 Research competitor"
    r = h.submit({"name": "Azure", "market_share": "23%", "key_differentiator": "Enterprise integration with Microsoft 365"})
    assert r
    r = h.submit({"strengths": ["Enterprise relationships", "Hybrid cloud", "Azure AD"], "weaknesses": ["Complex pricing", "Portal UX"]})
    assert r
    r = h.submit({"pricing_model": "Pay-as-you-go + reserved instances", "kubernetes_score": "7/10"})
    assert r

    assert h.step == "3.1 Create comparison matrix"


def test_empty_competitor_list(harness_factory):
    """Niche quantum computing compiler market: no direct competitors identified yet."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": []},
    )
    r = h.start()
    assert r

    r = h.submit({
        "criteria": ["qubit support", "error correction", "classical-quantum hybrid"],
        "market": "Quantum computing compiler toolchains",
    })
    assert r
    r = h.submit({
        "competitors": [],
        "note": "No direct competitors in quantum error-corrected compiler space; market too nascent",
    })
    assert r

    # Loop exits immediately
    assert h.step == "3.1 Create comparison matrix"
    assert h.status == "running"


def test_stop_then_resume(harness_factory):
    """Pause video conferencing tool comparison for team offsite, resume after."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "criteria": ["max participants", "recording", "breakout rooms", "pricing", "security certifications"],
        "market": "Enterprise video conferencing",
    })
    assert r
    assert r.new_step == "1.2 Identify competitors"
    assert h.step == "1.2 Identify competitors"

    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "1.2 Identify competitors"

    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "1.2 Identify competitors"

    r = h.submit({
        "competitors": [{"name": "Zoom Workplace", "tier": "Leader"}],
    })
    assert r
    assert r.new_step == "2.1 Research competitor"
    assert h.step == "2.1 Research competitor"


def test_complete_then_reset(harness_factory):
    """Finish food delivery competitive analysis, reset for ride-sharing market study."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    r = h.start()
    assert r

    # Fast path to done
    r = h.submit({"criteria": ["delivery_speed", "restaurant_selection", "driver_pay", "commission_rates"]})
    assert r
    r = h.submit({"competitors": [{"name": "DoorDash", "market_share": "67%"}]})
    assert r
    r = h.submit({"name": "DoorDash", "revenue": "$8.6B", "drivers": "6M+"})
    assert r
    r = h.submit({"strengths": ["Market dominance", "DashPass loyalty"], "weaknesses": ["Thin margins", "Driver churn"]})
    assert r
    r = h.submit({"commission_rate": "15-30%", "delivery_fee_range": "$1.99-5.99"})
    assert r
    r = h.submit({"matrix": {"DoorDash": {"speed": 8, "selection": 9, "pricing": 6}}})
    assert r
    r = h.submit({"insight": "DoorDash dominates but vulnerable on pricing transparency"})
    assert r
    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("3.4 Write final report")
    assert r
    r = h.submit({"report_title": "Food Delivery Competitive Landscape 2024", "pages": 18})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define analysis criteria"
    assert h.status == "running"


def test_goto_to_comparison(harness_factory):
    """Research phase already done in spreadsheet -- jump to creating comparison matrix for password managers."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1", "c2"]},
    )
    r = h.start()
    assert r

    r = h.goto("3.1 Create comparison matrix")
    assert r
    assert r.new_step == "3.1 Create comparison matrix"
    assert h.step == "3.1 Create comparison matrix"
    assert h.status == "running"

    r = h.submit({
        "matrix": {
            "1Password": {"security": 9, "ux": 9, "pricing": 6, "enterprise": 8},
            "Bitwarden": {"security": 9, "ux": 7, "pricing": 10, "enterprise": 6},
        },
        "dimensions": ["Security audit", "User experience", "Pricing value", "Enterprise features"],
    })
    assert r
    assert r.new_step == "3.2 Generate insights"
    assert h.step == "3.2 Generate insights"


def test_back(harness_factory):
    """Realize email marketing criteria incomplete -- go back to add deliverability metrics."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "criteria": ["templates", "automation", "pricing"],
        "note": "Forgot to include deliverability rate as criterion",
    })
    assert r
    assert r.new_step == "1.2 Identify competitors"
    assert h.step == "1.2 Identify competitors"

    r = h.back()
    assert r
    assert r.new_step == "1.1 Define analysis criteria"
    assert h.step == "1.1 Define analysis criteria"

    r = h.submit({
        "criteria": ["templates", "automation", "pricing", "deliverability_rate", "list_management"],
        "note": "Added deliverability and list management after team feedback",
    })
    assert r
    assert r.new_step == "1.2 Identify competitors"
    assert h.step == "1.2 Identify competitors"


def test_consecutive_backs(harness_factory):
    """Bouncing between matrix and insights on analytics platform comparison -- refining both iteratively.

    back() finds the most recent different step in history.
    After one back, the next back finds the step we just left.
    """
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    r = h.start()
    assert r

    # Advance to insights
    r = h.submit({"criteria": ["real-time analytics", "data warehouse support", "pricing"]})
    assert r
    r = h.submit({"competitors": [{"name": "Amplitude"}]})
    assert r
    r = h.submit({"name": "Amplitude", "market_segment": "Product analytics"})
    assert r
    r = h.submit({"strengths": ["Behavioral cohorts", "Event-based model"], "weaknesses": ["Expensive at scale"]})
    assert r
    r = h.submit({"pricing": "Usage-based, starts at $49K/year for Growth plan"})
    assert r
    r = h.submit({"matrix": {"Amplitude": {"real_time": 8, "warehouse": 7, "pricing": 4}}})
    assert r
    assert h.step == "3.2 Generate insights"

    r = h.back()
    assert r
    assert r.new_step == "3.1 Create comparison matrix"
    assert h.step == "3.1 Create comparison matrix"

    # Second back bounces to 3.2 (most recent different step in history)
    r = h.back()
    assert r
    assert r.new_step == "3.2 Generate insights"
    assert h.step == "3.2 Generate insights"


# ===============================================================
# New multi-dimension tests
# ===============================================================

def test_data_accumulates_through_phases(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    h.start()

    h.submit({"criteria": "market share, pricing, features"})
    data = h.state.data
    assert "1.1 Define analysis criteria" in data
    assert data["1.1 Define analysis criteria"]["criteria"] == "market share, pricing, features"

    h.submit({"competitors_list": ["Alpha", "Beta"]})
    data = h.state.data
    assert "1.2 Identify competitors" in data


def test_data_accumulates_in_loop(harness_factory):
    """Data submitted during loop iterations persists."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1", "c2"]},
    )
    _advance_to_competitor_loop(h)

    h.submit({"research": "c1 data"})
    data = h.state.data
    assert "2.1 Research competitor" in data
    assert data["2.1 Research competitor"]["research"] == "c1 data"


def test_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected actions."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    _advance_to_competitor_loop(h)
    _do_one_competitor(h)  # completes loop (only 1 competitor)
    assert h.step == "3.1 Create comparison matrix"
    h.submit({})  # 3.1 -> 3.2
    h.submit({})  # 3.2 -> 3.3
    assert h.step == "3.3 Review"
    h.approve()
    h.submit_goto("3.4 Write final report")
    h.submit({})  # 3.4 -> Done
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "approve" in actions
    assert "terminate" in actions[-1]


def test_cross_executor_at_competitor_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state persists."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1", "c2", "c3"]},
    )
    _advance_to_competitor_loop(h)

    # Complete first competitor
    _do_one_competitor(h)
    assert h.step == "2.1 Research competitor"

    h.new_executor()

    assert h.step == "2.1 Research competitor"
    loop_info = h.state.loop_state.get("2.0 Competitor loop")
    assert loop_info is not None
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_cross_executor_at_review(harness_factory):
    """Close executor at review wait step, reopen, state persists."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    _advance_to_competitor_loop(h)
    _do_one_competitor(h)
    h.submit({})  # 3.1 -> 3.2
    h.submit({})  # 3.2 -> 3.3
    assert h.step == "3.3 Review"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "3.3 Review"
    assert h.status == "waiting"


def test_node_validates_research(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    _advance_to_competitor_loop(h)

    h.register_node(
        "2.1 Research competitor",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("name") else "must include competitor name",
        ),
    )

    r = h.submit({"notes": "some notes"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"name": "CompetitorX"})
    assert r
    assert r.new_step == "2.2 Analyze strengths and weaknesses"


def test_node_archives_findings(harness_factory):
    """Archive node writes competitor findings to SQLite table."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1", "c2"]},
    )
    _advance_to_competitor_loop(h)

    h.register_node(
        "2.3 Document findings",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"competitor": "string", "rating": "string"}},
            archive={"table": "competitor_findings"},
        ),
    )

    # Competitor 1
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit({"competitor": "Alpha", "rating": "strong"})

    # Competitor 2
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit({"competitor": "Beta", "rating": "weak"})

    rows = h.get_archived_rows("competitor_findings")
    assert len(rows) == 2
    assert rows[0]["competitor"] == "Alpha"
    assert rows[1]["competitor"] == "Beta"


def test_submit_on_waiting_review_fails(harness_factory):
    """Submit while review step is waiting returns failure."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    _advance_to_competitor_loop(h)
    _do_one_competitor(h)
    h.submit({})  # 3.1
    h.submit({})  # 3.2
    assert h.step == "3.3 Review"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    _advance_to_competitor_loop(h)

    h.save_checkpoint("at_loop")

    _do_one_competitor(h)
    assert h.step == "3.1 Create comparison matrix"

    restored = h.load_checkpoint("at_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Research competitor"


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    h.start()
    h.submit({})  # 1.1 -> 1.2
    assert h.step == "1.2 Identify competitors"

    r = h.retry()
    assert r
    assert h.step == "1.2 Identify competitors"
    assert h.status == "running"


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
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
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    h.start()
    h.goto("3.4 Write final report")
    h.submit({})
    assert h.step == "Done"
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define analysis criteria"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    _advance_to_competitor_loop(h)
    assert h.step == "2.1 Research competitor"

    h.register_node(
        "2.1 Research competitor",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nResearch the competitor thoroughly.\n\n## Steps\n1. Gather data\n2. Document findings",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy in status."""
    h = harness_factory(
        "p4-competitive-analysis.yaml",
        loop_data={"competitors": ["c1"]},
    )
    h.start()
    assert h.step == "1.1 Define analysis criteria"

    h.register_node(
        "1.1 Define analysis criteria",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="block",
                patterns=[
                    EditPolicyPattern(glob="docs/**", policy="silent"),
                ],
            ),
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["edit_policy"] is not None
    assert status["node"]["edit_policy"]["default"] == "block"
