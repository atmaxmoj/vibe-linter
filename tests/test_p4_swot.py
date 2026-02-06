"""SWOT Analysis workflow tests (p4-swot.yaml).

Tests the linear S-W-O-T flow with review containing
multi-target fallback to specific quadrants.
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, EditPolicyPattern, NodeDefinition

# --- Helpers ---

def _advance_to_review(h):
    """Start -> submit through 6 steps to reach 1.7 Review (waiting)."""
    h.start()
    for _ in range(6):
        h.submit({})
    assert h.step == "1.7 Review"
    assert h.status == "waiting"


# ===============================================================
# Existing tests (unchanged)
# ===============================================================

def test_complete_smoothly(harness_factory):
    """Full SWOT analysis for Patagonia entering the direct-to-consumer rental/resale market."""
    h = harness_factory("p4-swot.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Analyze Strengths"
    assert h.status == "running"

    r = h.submit({
        "company": "Patagonia",
        "strengths": [
            "Brand loyalty and trust among environmentally conscious consumers (NPS 72)",
            "Worn Wear repair program already handling 100K+ items/year",
            "Vertical integration: owns factories, controls quality end-to-end",
            "Strong sustainability narrative provides authentic positioning for circular economy",
            "Existing e-commerce infrastructure with $1.5B annual revenue",
        ],
    })
    assert r
    assert r.new_step == "1.2 Analyze Weaknesses"
    assert h.step == "1.2 Analyze Weaknesses"

    r = h.submit({
        "weaknesses": [
            "Premium pricing limits addressable market for rental ($15-40/item/week)",
            "No experience in logistics-heavy rental operations (inventory tracking, cleaning, returns)",
            "Current IT systems not built for rental inventory management",
            "Retail staff lack training in rental program operations",
            "Limited data on customer willingness to rent vs buy outdoor gear",
        ],
    })
    assert r
    assert r.new_step == "1.3 Analyze Opportunities"
    assert h.step == "1.3 Analyze Opportunities"

    r = h.submit({
        "opportunities": [
            "Circular economy market projected to reach $712B by 2026 (Ellen MacArthur Foundation)",
            "Gen Z spending on secondhand up 20% YoY -- cultural shift toward access over ownership",
            "Partnership potential with REI Co-op for shared rental logistics network",
            "B Corp certification creates natural trust moat in sustainability-driven commerce",
            "EU textile sustainability regulations (2025) will push competitors toward circular models",
        ],
    })
    assert r
    assert r.new_step == "1.4 Analyze Threats"
    assert h.step == "1.4 Analyze Threats"

    r = h.submit({
        "threats": [
            "The North Face (VF Corp) launched rental pilot in Q3 2024 with aggressive pricing",
            "Rent the Runway's outdoor expansion targeting same demographic",
            "Amazon's recommerce ambitions could commoditize secondhand outdoor gear",
            "Economic downturn could make customers prioritize cheap fast fashion over premium rentals",
            "Cannibalization risk: rental may reduce full-price sales by 8-15% (internal modeling)",
        ],
    })
    assert r
    assert r.new_step == "1.5 Create SWOT matrix"
    assert h.step == "1.5 Create SWOT matrix"

    r = h.submit({
        "matrix_format": "2x2 with cross-impact scoring",
        "so_strategies": ["Leverage Worn Wear brand equity to launch 'Patagonia Borrow' rental line"],
        "wo_strategies": ["Partner with logistics provider (Returnly/Loop) to overcome operational gap"],
        "st_strategies": ["Launch before TNF scales their pilot; first-mover in premium outdoor rental"],
        "wt_strategies": ["Pilot in 5 cities before committing to nationwide rollout to limit downside"],
    })
    assert r
    assert r.new_step == "1.6 Generate strategic recommendations"
    assert h.step == "1.6 Generate strategic recommendations"

    r = h.submit({
        "recommendations": [
            "Phase 1: Launch 'Patagonia Borrow' in SF, Portland, Boulder, Seattle, Denver (Q2 2025)",
            "Phase 2: Partner with REI for drop-off/pickup logistics network expansion",
            "Phase 3: Integrate rental into main e-commerce platform with 'Rent or Buy' toggle",
            "Pricing: $12-35/week based on item MSRP, with purchase credit after 4th rental",
        ],
        "success_metrics": ["Rental program NPS > 60", "30% repeat rental rate", "<8% full-price cannibalization"],
    })
    assert r
    assert r.new_step == "1.7 Review"
    assert h.step == "1.7 Review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_review_back_to_strengths(harness_factory):
    """Tesla FSD SWOT review: strengths section overestimates autonomy level. Redo from strengths."""
    h = harness_factory("p4-swot.yaml")
    r = h.start()
    assert r

    # Advance to review
    r = h.submit({"strengths": ["Full self-driving capability", "OTA updates", "Data flywheel from 5M+ vehicles"]})
    r = h.submit({"weaknesses": ["Regulatory uncertainty", "Quality control issues", "Key-person risk"]})
    r = h.submit({"opportunities": ["Robotaxi market", "Energy storage", "AI licensing"]})
    r = h.submit({"threats": ["Chinese EV competition", "Interest rate impact on sales", "Waymo progress"]})
    r = h.submit({"matrix": "2x2 with quantified impact scores"})
    r = h.submit({"recommendations": ["Accelerate FSD rollout", "Enter India market"]})
    assert r
    assert h.step == "1.7 Review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto -- strengths overstated FSD capabilities
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("1.1 Analyze Strengths")
    assert r
    assert r.new_step == "1.1 Analyze Strengths"
    assert h.step == "1.1 Analyze Strengths"
    assert h.status == "running"

    # Redo from strengths through all with corrected data
    r = h.submit({"strengths": ["Level 2+ ADAS (not full autonomy)", "OTA updates", "Data flywheel", "Supercharger network"]})
    r = h.submit({"weaknesses": ["FSD is Level 2, not Level 4", "Regulatory scrutiny from NHTSA", "Quality control"]})
    r = h.submit({"opportunities": ["Robotaxi licensing (2027+)", "Energy arbitrage", "AI compute for third parties"]})
    r = h.submit({"threats": ["BYD pricing pressure", "Waymo achieving Level 4 first", "EU carbon credit revenue declining"]})
    r = h.submit({"matrix": "Corrected 2x2 with realistic autonomy assessment"})
    r = h.submit({"recommendations": ["Focus on Level 3 regulatory approval", "Diversify revenue beyond auto sales"]})
    assert r
    assert h.step == "1.7 Review"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_review_goto_specific_quadrant(harness_factory):
    """Netflix SWOT: reviewer flags that opportunities section missed gaming market expansion."""
    h = harness_factory("p4-swot.yaml")
    r = h.start()
    assert r

    # Advance to review with Netflix data
    r = h.submit({"strengths": ["240M+ global subscribers", "Content spend $17B/year", "Recommendation algorithm"]})
    r = h.submit({"weaknesses": ["Password sharing crackdown backlash", "Debt-funded content", "No live sports"]})
    r = h.submit({"opportunities": ["Ad-supported tier growth", "International expansion in SE Asia"]})
    r = h.submit({"threats": ["Disney+ bundling", "Apple TV+ pricing", "Regional players like Viu"]})
    r = h.submit({"matrix": "2x2 with competitive impact weighting"})
    r = h.submit({"recommendations": ["Expand AVOD tier", "Acquire gaming studio"]})
    assert r
    assert h.step == "1.7 Review"

    # WAIT+LLM: reviewer says opportunities missed gaming and live events
    r = h.approve()
    assert r
    r = h.submit_goto("1.3 Analyze Opportunities")
    assert r
    assert r.new_step == "1.3 Analyze Opportunities"
    assert h.step == "1.3 Analyze Opportunities"
    assert h.status == "running"


def test_stop_then_resume(harness_factory):
    """Shopify SWOT: analyst pauses mid-analysis during the opportunities quadrant to gather market data."""
    h = harness_factory("p4-swot.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "company": "Shopify",
        "strengths": [
            "1.7M+ merchants on platform globally",
            "Shopify Payments captures 56% of GMV",
            "Developer ecosystem with 8,000+ apps",
        ],
    })
    assert r
    r = h.submit({
        "weaknesses": [
            "Enterprise tier (Shopify Plus) lags behind Salesforce Commerce Cloud",
            "Fulfillment network shut down in 2023 after $1B+ investment",
            "Heavy reliance on SMB segment vulnerable to economic downturns",
        ],
    })
    assert r
    assert h.step == "1.3 Analyze Opportunities"

    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "1.3 Analyze Opportunities"

    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "1.3 Analyze Opportunities"

    r = h.submit({
        "opportunities": [
            "B2B commerce market ($7.7T TAM) -- Shopify B2B launched 2023",
            "AI-powered storefront personalization (Shopify Magic/Sidekick)",
            "Headless commerce via Hydrogen/Oxygen stack",
        ],
    })
    assert r
    assert r.new_step == "1.4 Analyze Threats"
    assert h.step == "1.4 Analyze Threats"


def test_skip_a_quadrant(harness_factory):
    """Spotify SWOT: weaknesses already documented in Q3 board report, skip to opportunities."""
    h = harness_factory("p4-swot.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "company": "Spotify",
        "strengths": [
            "615M MAU and 239M premium subscribers (Q3 2024)",
            "Discovery algorithms (Release Radar, Discover Weekly) drive 31% of all streams",
            "Podcast market leader with 5M+ shows",
        ],
    })
    assert r
    assert r.new_step == "1.2 Analyze Weaknesses"
    assert h.step == "1.2 Analyze Weaknesses"

    r = h.skip("Weaknesses covered in Q3 2024 board report -- high royalty costs (72% of revenue), podcast profitability still negative")
    assert r
    assert r.new_step == "1.3 Analyze Opportunities"
    assert h.step == "1.3 Analyze Opportunities"
    assert h.status == "running"


def test_complete_then_reset(harness_factory):
    """Complete Airbnb SWOT, then reset to analyze competitor Vrbo."""
    h = harness_factory("p4-swot.yaml")
    r = h.start()
    assert r

    r = h.submit({"company": "Airbnb", "strengths": ["7M+ active listings", "Trust via reviews/Superhost", "Experiences product line"]})
    r = h.submit({"weaknesses": ["Regulatory crackdowns in NYC/Barcelona", "Host quality inconsistency", "Customer service complaints"]})
    r = h.submit({"opportunities": ["Long-term stays (28+ days now 18% of bookings)", "Luxury segment via Airbnb Luxe", "Corporate travel partnerships"]})
    r = h.submit({"threats": ["Hotel chains launching home-sharing (Marriott Homes & Villas)", "Insurance liability from guest damage", "Housing affordability backlash"]})
    r = h.submit({"matrix": "2x2 weighted by revenue impact", "key_insight": "Regulatory risk is top-left high-impact threat"})
    r = h.submit({"recommendations": ["Invest in host compliance tools", "Expand Luxe to top 50 markets", "Launch corporate booking portal"]})
    assert r

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"

    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Analyze Strengths"
    assert h.status == "running"


def test_back(harness_factory):
    """Zoom SWOT: after analyzing opportunities, go back to add a missed weakness."""
    h = harness_factory("p4-swot.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "company": "Zoom",
        "strengths": ["Brand synonymous with video conferencing", "95% customer satisfaction (Gartner)", "Simple UX, low friction onboarding"],
    })
    assert r
    assert r.new_step == "1.2 Analyze Weaknesses"
    assert h.step == "1.2 Analyze Weaknesses"

    r = h.submit({
        "weaknesses": ["Revenue concentration in meetings (78%)", "Enterprise security perception post-Zoombombing"],
    })
    assert r
    assert r.new_step == "1.3 Analyze Opportunities"
    assert h.step == "1.3 Analyze Opportunities"

    # Realized we missed a critical weakness (churn from Teams bundling)
    r = h.back()
    assert r
    assert r.new_step == "1.2 Analyze Weaknesses"
    assert h.step == "1.2 Analyze Weaknesses"

    r = h.submit({
        "weaknesses": [
            "Revenue concentration in meetings (78%)",
            "Enterprise security perception post-Zoombombing",
            "Microsoft Teams bundled free with M365 driving 30% SMB churn",
        ],
    })
    assert r
    assert r.new_step == "1.3 Analyze Opportunities"
    assert h.step == "1.3 Analyze Opportunities"


def test_consecutive_back_bounces(harness_factory):
    """NVIDIA SWOT: analyst bounces between threats and matrix while cross-referencing AMD/Intel data.

    back() finds the most recent different step in history.
    After one back, the next back returns to the step we just left.
    """
    h = harness_factory("p4-swot.yaml")
    r = h.start()
    assert r

    r = h.submit({"company": "NVIDIA", "strengths": ["92% data center GPU market share", "CUDA ecosystem lock-in", "Full-stack AI platform (DGX, Networking, Software)"]})
    assert r
    r = h.submit({"weaknesses": ["Customer concentration (Microsoft/Meta/Google = 40% revenue)", "China export restrictions reduce TAM by $10B+"]})
    assert r
    r = h.submit({"opportunities": ["Sovereign AI infrastructure ($30B+ pipeline)", "Automotive autonomous driving ($8B TAM by 2028)"]})
    assert r
    r = h.submit({"threats": ["AMD MI300X gaining traction at hyperscalers", "Google/Amazon custom silicon (TPU, Trainium)", "Potential antitrust scrutiny over CUDA bundling"]})
    assert r
    assert h.step == "1.5 Create SWOT matrix"

    # Need to cross-reference threat data while building matrix
    r = h.back()
    assert r
    assert r.new_step == "1.4 Analyze Threats"
    assert h.step == "1.4 Analyze Threats"

    # Second back bounces to 1.5 (most recent different step in history)
    r = h.back()
    assert r
    assert r.new_step == "1.5 Create SWOT matrix"
    assert h.step == "1.5 Create SWOT matrix"


def test_goto(harness_factory):
    """Stripe SWOT: quadrant data already loaded from prior session, jump to matrix creation."""
    h = harness_factory("p4-swot.yaml")
    r = h.start()
    assert r

    r = h.goto("1.5 Create SWOT matrix")
    assert r
    assert r.new_step == "1.5 Create SWOT matrix"
    assert h.step == "1.5 Create SWOT matrix"
    assert h.status == "running"

    r = h.submit({
        "matrix": "2x2 with revenue-impact weighting",
        "so_strategies": ["Leverage developer ecosystem to capture embedded finance ($7T market)"],
        "wo_strategies": ["Build enterprise sales team to compete with Adyen in large-merchant segment"],
        "st_strategies": ["Diversify beyond payments into Stripe Treasury/Issuing before bank-as-a-service entrants"],
        "wt_strategies": ["Reduce geographic concentration by prioritizing India/Brazil expansion"],
    })
    assert r
    assert r.new_step == "1.6 Generate strategic recommendations"
    assert h.step == "1.6 Generate strategic recommendations"


def test_modify_yaml(harness_factory):
    """Meta SWOT: add a prioritization step to rank findings by revenue impact before recommendations."""
    h = harness_factory("p4-swot.yaml")
    r = h.start()
    assert r

    r = h.submit({"company": "Meta Platforms", "strengths": ["3.27B daily active people across family of apps", "AI-driven ad targeting despite ATT", "Reality Labs VR hardware lead"]})
    assert r
    r = h.submit({"weaknesses": ["Reality Labs $13.7B annual losses", "Regulatory fines (EU DMA compliance)", "Youth engagement declining vs TikTok"]})
    assert r
    r = h.submit({"opportunities": ["Business messaging monetization (WhatsApp Business)", "AI assistants integrated into messaging", "Creator economy tools (Reels monetization)"]})
    assert r
    r = h.submit({"threats": ["TikTok capturing 25-34 demographic", "EU Digital Markets Act fines up to 10% global revenue", "Apple privacy changes reducing ad precision"]})
    assert r
    assert h.step == "1.5 Create SWOT matrix"

    modified_yaml = """\u540d\u79f0: SWOT Analysis
\u63cf\u8ff0: Modified with prioritization

\u6b65\u9aa4:
  - 1.1 Analyze Strengths

  - 1.2 Analyze Weaknesses

  - 1.3 Analyze Opportunities

  - 1.4 Analyze Threats

  - 1.5 Create SWOT matrix

  - 1.55 Prioritize findings:
      \u4e0b\u4e00\u6b65: 1.6 Generate strategic recommendations

  - 1.6 Generate strategic recommendations

  - 1.7 Review:
      \u7c7b\u578b: wait
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "SWOT analysis is complete and accurate"
          \u53bb: Done
        - \u5982\u679c: "strengths section needs work"
          \u53bb: 1.1 Analyze Strengths
        - \u5982\u679c: "opportunities section needs more research"
          \u53bb: 1.3 Analyze Opportunities
        - \u53bb: 1.1 Analyze Strengths

  - Done:
      \u7c7b\u578b: terminate
"""
    h.reload_yaml(modified_yaml)

    r = h.submit({
        "matrix": "2x2 with revenue-weighted scoring",
        "key_crossover": "Reality Labs losses are a weakness, but VR/AR opportunity could be $100B+ by 2030",
    })
    assert r
    assert r.new_step == "1.55 Prioritize findings"
    assert h.step == "1.55 Prioritize findings"

    r = h.submit({
        "priority_ranking": [
            "1. Ad revenue resilience (strength + threat interaction)",
            "2. Reality Labs investment decision (weakness + opportunity)",
            "3. Regulatory compliance cost (weakness + threat)",
        ],
    })
    assert r
    assert r.new_step == "1.6 Generate strategic recommendations"
    assert h.step == "1.6 Generate strategic recommendations"


# ===============================================================
# New multi-dimension tests
# ===============================================================

def test_data_accumulates_through_quadrants(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p4-swot.yaml")
    h.start()

    h.submit({"strengths": ["brand recognition", "technology"]})
    data = h.state.data
    assert "1.1 Analyze Strengths" in data
    assert data["1.1 Analyze Strengths"]["strengths"] == ["brand recognition", "technology"]

    h.submit({"weaknesses": ["high costs"]})
    data = h.state.data
    assert "1.2 Analyze Weaknesses" in data
    assert data["1.2 Analyze Weaknesses"]["weaknesses"] == ["high costs"]

    h.submit({"opportunities": ["emerging markets"]})
    data = h.state.data
    assert "1.3 Analyze Opportunities" in data

    h.submit({"threats": ["new competitors"]})
    data = h.state.data
    assert "1.4 Analyze Threats" in data


def test_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected actions."""
    h = harness_factory("p4-swot.yaml")
    _advance_to_review(h)
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "approve" in actions
    assert "terminate" in actions[-1]


def test_cross_executor_at_matrix(harness_factory):
    """Close executor mid-analysis, reopen, state persists."""
    h = harness_factory("p4-swot.yaml")
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 1.3
    h.submit({})  # 1.3 -> 1.4
    h.submit({})  # 1.4 -> 1.5
    assert h.step == "1.5 Create SWOT matrix"

    h.new_executor()

    assert h.step == "1.5 Create SWOT matrix"
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert r.new_step == "1.6 Generate strategic recommendations"


def test_cross_executor_at_review(harness_factory):
    """Close executor at review wait step, reopen, state persists."""
    h = harness_factory("p4-swot.yaml")
    _advance_to_review(h)

    h.new_executor()

    assert h.step == "1.7 Review"
    assert h.status == "waiting"

    h.approve()
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_node_validates_strengths(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p4-swot.yaml")
    h.start()
    assert h.step == "1.1 Analyze Strengths"

    h.register_node(
        "1.1 Analyze Strengths",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("strengths") else "must include strengths list",
        ),
    )

    r = h.submit({"notes": "thinking about strengths"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"strengths": ["innovation", "brand"]})
    assert r
    assert r.new_step == "1.2 Analyze Weaknesses"


def test_node_archives_matrix(harness_factory):
    """Archive node writes SWOT matrix data to SQLite table."""
    h = harness_factory("p4-swot.yaml")
    h.start()
    for _ in range(4):
        h.submit({})
    assert h.step == "1.5 Create SWOT matrix"

    h.register_node(
        "1.5 Create SWOT matrix",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"quadrant": "string", "items_count": "string"}},
            archive={"table": "swot_matrix"},
        ),
    )

    r = h.submit({"quadrant": "all", "items_count": "16"})
    assert r

    rows = h.get_archived_rows("swot_matrix")
    assert len(rows) == 1
    assert rows[0]["quadrant"] == "all"
    assert rows[0]["items_count"] == "16"


def test_submit_on_waiting_review_fails(harness_factory):
    """Submit while review step is waiting returns failure."""
    h = harness_factory("p4-swot.yaml")
    _advance_to_review(h)

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p4-swot.yaml")
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p4-swot.yaml")
    h.start()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p4-swot.yaml")
    h.start()
    h.submit({"strengths": ["a"]})
    h.submit({"weaknesses": ["b"]})
    assert h.step == "1.3 Analyze Opportunities"

    h.save_checkpoint("at_opportunities")

    h.submit({})
    h.submit({})
    assert h.step == "1.5 Create SWOT matrix"

    restored = h.load_checkpoint("at_opportunities")
    assert restored is not None
    assert restored.current_step == "1.3 Analyze Opportunities"
    assert "1.2 Analyze Weaknesses" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p4-swot.yaml")
    h.start()
    h.submit({})  # 1.1 -> 1.2
    assert h.step == "1.2 Analyze Weaknesses"

    r = h.retry()
    assert r
    assert h.step == "1.2 Analyze Weaknesses"
    assert h.status == "running"


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p4-swot.yaml")
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p4-swot.yaml")
    h.start()
    h.submit({})
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p4-swot.yaml")
    _advance_to_review(h)
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p4-swot.yaml")

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Analyze Strengths"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p4-swot.yaml")
    h.start()
    assert h.step == "1.1 Analyze Strengths"

    h.register_node(
        "1.1 Analyze Strengths",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nIdentify company strengths.\n\n## Steps\n1. List internal advantages\n2. Document competitive edges",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy in status."""
    h = harness_factory("p4-swot.yaml")
    h.start()
    assert h.step == "1.1 Analyze Strengths"

    h.register_node(
        "1.1 Analyze Strengths",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="block",
                patterns=[
                    EditPolicyPattern(glob="analysis/**", policy="silent"),
                ],
            ),
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["edit_policy"] is not None
    assert status["node"]["edit_policy"]["default"] == "block"
