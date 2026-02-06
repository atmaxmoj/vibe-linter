"""Keyword-First Workflow tests (p5-keyword-first.yaml).

Tests the multi-wait flow with topic/keyword/outline/final review,
section loop, and review fallback.
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# --- Helpers ---

def _advance_to_section_loop(h):
    """Start -> approve topic -> keyword research -> approve keywords -> outline -> approve outline -> enter loop."""
    h.start()
    h.approve({})         # 1.1 (wait) -> 1.2
    h.submit({})          # 1.2 -> 1.3
    h.approve()           # 1.3 (wait+LLM) -> running
    h.submit_goto("1.4 Write outline")  # 1.3 -> 1.4
    h.submit({})          # 1.4 -> 1.5
    h.approve()           # 1.5 (wait+LLM) -> running
    h.submit_goto("2.0 Section loop")  # 1.5 -> 2.0 -> 2.1
    assert h.step == "2.1 Write section draft"


def _do_one_section(h):
    """At 2.1, complete one section cycle (2.1 -> 2.2 -> 2.3 -> loop)."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit_goto("2.0 Section loop")  # 2.3 -> loop header


# ===============================================================
# Existing tests (unchanged)
# ===============================================================

def test_write_one_article_complete(harness_factory):
    """Write a complete guide on 'best project management software for remote teams' -- high CPC keyword."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro", "body", "conclusion"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Choose topic"
    assert h.status == "waiting"

    r = h.approve({
        "topic": "Best Project Management Software for Remote Teams",
        "content_type": "listicle with comparison table",
        "target_audience": "remote team leads and ops managers",
        "business_goal": "affiliate revenue from PM tool signups",
    })
    assert r
    assert r.new_step == "1.2 Keyword research"
    assert h.step == "1.2 Keyword research"
    assert h.status == "running"

    r = h.submit({
        "primary_keyword": "best project management software",
        "search_volume": 18100,
        "keyword_difficulty": 72,
        "cpc": "$12.40",
        "secondary_keywords": [
            {"kw": "project management tools for remote teams", "vol": 2400, "kd": 45},
            {"kw": "best PM software 2025", "vol": 1900, "kd": 38},
            {"kw": "asana vs monday vs clickup", "vol": 3600, "kd": 52},
        ],
        "serp_analysis": "Top 3 results are Forbes Advisor, G2, and Zapier -- all listicle format, 3000-5000 words",
    })
    assert r
    assert r.new_step == "1.3 Keyword review"
    assert h.step == "1.3 Keyword review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("1.4 Write outline")
    assert r
    assert r.new_step == "1.4 Write outline"
    assert h.step == "1.4 Write outline"

    r = h.submit({
        "outline": {
            "h1": "13 Best Project Management Software for Remote Teams (2025)",
            "sections": [
                "Introduction: Why remote teams need specialized PM tools",
                "Comparison table: Quick-glance feature matrix for all 13 tools",
                "Conclusion: How to choose the right PM tool for your team size",
            ],
            "target_word_count": 4500,
            "internal_links_planned": ["/remote-work-tools/", "/asana-review/", "/monday-review/"],
        },
    })
    assert r
    assert r.new_step == "1.5 Outline review"
    assert h.step == "1.5 Outline review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("2.0 Section loop")
    assert r
    assert h.step == "2.1 Write section draft"

    # Write 3 sections
    section_data = [
        {"section": "intro", "word_count": 450, "draft": "Remote work is no longer a perk -- it is the default..."},
        {"section": "comparison_table", "word_count": 2800, "draft": "| Tool | Price | Best For | Integrations |..."},
        {"section": "conclusion", "word_count": 600, "draft": "Choosing the right PM software depends on three factors..."},
    ]
    seo_data = [
        {"keywords_placed": ["best project management software", "remote team PM tools"], "density": "1.2%", "meta_desc": True},
        {"keywords_placed": ["asana vs monday vs clickup", "PM software comparison"], "density": "0.8%", "schema_markup": "comparison_table"},
        {"keywords_placed": ["best PM software 2025", "choose project management tool"], "density": "1.0%", "cta_added": True},
    ]
    for i in range(3):
        assert h.step == "2.1 Write section draft"
        r = h.submit(section_data[i])
        assert r
        assert r.new_step == "2.2 Optimize for SEO"
        assert h.step == "2.2 Optimize for SEO"
        r = h.submit(seo_data[i])
        assert r
        assert r.new_step == "2.3 Section quality check"
        assert h.step == "2.3 Section quality check"
        r = h.submit_goto("2.0 Section loop")
        assert r
        if i < 2:
            assert h.step == "2.1 Write section draft"

    assert h.step == "3.1 Assemble full article"

    r = h.submit({
        "total_word_count": 3850,
        "internal_links": 3,
        "external_links": 8,
        "images": 4,
        "schema_types": ["Article", "ItemList", "FAQPage"],
    })
    assert r
    assert r.new_step == "3.2 Final review"
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_section_bad_loop_retry(harness_factory):
    """'How to start a podcast' intro section fails quality twice (thin content, no keyword), passes on third try."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    r = h.start()
    assert r

    # Approve topic (WAIT-ONLY), keywords (WAIT+LLM), outline (WAIT+LLM)
    r = h.approve({"topic": "How to Start a Podcast in 2025"})
    assert r
    r = h.submit({"primary_keyword": "how to start a podcast", "search_volume": 33100, "kd": 65})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.4 Write outline")
    assert r
    r = h.submit({"outline": {"h1": "How to Start a Podcast: Complete Beginner Guide (2025)", "sections": ["intro"]}})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r

    # First attempt: too thin (only 120 words), quality check fails
    r = h.submit({"section": "intro", "word_count": 120, "draft": "Podcasting is popular. Here is how to start."})
    assert r
    r = h.submit({"keywords_placed": [], "density": "0%"})
    assert r
    assert h.step == "2.3 Section quality check"
    r = h.submit_goto("2.1 Write section draft")
    assert r
    assert r.new_step == "2.1 Write section draft"
    assert h.step == "2.1 Write section draft"

    # Second attempt: better length but keyword density too low
    r = h.submit({"section": "intro", "word_count": 380, "draft": "Starting a podcast can transform your career..."})
    assert r
    r = h.submit({"keywords_placed": ["podcast"], "density": "0.3%", "note": "primary keyword 'how to start a podcast' not in first 100 words"})
    assert r
    r = h.submit_goto("2.1 Write section draft")
    assert r
    assert h.step == "2.1 Write section draft"

    # Third attempt: passes both quality and SEO
    r = h.submit({"section": "intro", "word_count": 420, "draft": "Learning how to start a podcast is easier than ever in 2025..."})
    assert r
    r = h.submit({"keywords_placed": ["how to start a podcast", "podcasting for beginners"], "density": "1.1%", "flesch_score": 62})
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r
    assert h.step == "3.1 Assemble full article"


def test_final_review_rejects_back_to_sections(harness_factory):
    """'Kubernetes tutorial' article rejected at final review -- intro section needs E-E-A-T signals."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    r = h.start()
    assert r

    # Fast path to final review
    r = h.approve({"topic": "Kubernetes Tutorial for Beginners"})
    assert r
    r = h.submit({"primary_keyword": "kubernetes tutorial", "search_volume": 27100, "kd": 71})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.4 Write outline")
    assert r
    r = h.submit({"outline": {"h1": "Kubernetes Tutorial: From Zero to Production (2025)", "sections": ["intro"]}})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r
    r = h.submit({"section": "intro", "word_count": 500})
    assert r
    r = h.submit({"keywords_placed": ["kubernetes tutorial"], "density": "0.8%"})
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r
    r = h.submit({"total_word_count": 500, "readability_score": 58})
    assert r

    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    # Reviewer: intro lacks author credentials and real-world cluster examples (E-E-A-T)
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("2.0 Section loop")
    assert r
    assert h.step == "2.1 Write section draft"
    assert h.status == "running"


def test_keyword_review_rejected_reresearch(harness_factory):
    """'Home espresso machine' keywords rejected -- too broad, need long-tail. Redo research with buyer-intent focus."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    r = h.start()
    assert r

    r = h.approve({"topic": "Best Home Espresso Machines Under $500"})
    assert r
    r = h.submit({
        "primary_keyword": "espresso machine",
        "search_volume": 135000,
        "kd": 89,
        "note": "Too broad, KD too high for a new site",
    })
    assert r
    assert h.step == "1.3 Keyword review"
    assert h.status == "waiting"

    # Reviewer rejects: keyword too competitive, need long-tail buyer-intent keywords
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("1.2 Keyword research")
    assert r
    assert r.new_step == "1.2 Keyword research"
    assert h.step == "1.2 Keyword research"
    assert h.status == "running"

    # Research again with long-tail focus
    r = h.submit({
        "primary_keyword": "best espresso machine under 500",
        "search_volume": 4400,
        "kd": 42,
        "cpc": "$3.80",
        "secondary_keywords": [
            {"kw": "affordable espresso machine for beginners", "vol": 1200, "kd": 28},
            {"kw": "breville bambino vs gaggia classic", "vol": 880, "kd": 22},
        ],
    })
    assert r
    assert r.new_step == "1.3 Keyword review"
    assert h.step == "1.3 Keyword review"
    assert h.status == "waiting"

    # Now approved
    r = h.approve()
    assert r
    r = h.submit_goto("1.4 Write outline")
    assert r
    assert r.new_step == "1.4 Write outline"
    assert h.step == "1.4 Write outline"


def test_outline_rejected_rewrite(harness_factory):
    """'Python web scraping' outline rejected -- missing legal/ethical section. Rewrite with compliance angle."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    r = h.start()
    assert r

    r = h.approve({"topic": "Python Web Scraping Guide"})
    assert r
    r = h.submit({"primary_keyword": "python web scraping", "search_volume": 14800, "kd": 58})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.4 Write outline")
    assert r
    r = h.submit({
        "outline": {
            "h1": "Python Web Scraping: Ultimate Guide with BeautifulSoup & Scrapy",
            "sections": ["intro -- what is web scraping"],
            "note": "Missing legal/ethical considerations section",
        },
    })
    assert r
    assert h.step == "1.5 Outline review"
    assert h.status == "waiting"

    # Reviewer rejects: must include robots.txt compliance and GDPR considerations
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("1.4 Write outline")
    assert r
    assert r.new_step == "1.4 Write outline"
    assert h.step == "1.4 Write outline"
    assert h.status == "running"

    # Rewrite with legal/ethical section added
    r = h.submit({
        "outline": {
            "h1": "Python Web Scraping: Complete Guide with Legal Best Practices (2025)",
            "sections": ["intro -- why scrape responsibly, robots.txt, rate limiting, GDPR"],
            "added_sections": ["Legal & Ethical Web Scraping", "Respecting robots.txt and rate limits"],
        },
    })
    assert r
    assert r.new_step == "1.5 Outline review"
    assert h.step == "1.5 Outline review"

    # Now approved
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r
    assert h.step == "2.1 Write section draft"


def test_stop_mid_writing_resume(harness_factory):
    """'Email marketing best practices' article: stop during SEO optimization to wait for GSC data refresh."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro", "body"]},
    )
    r = h.start()
    assert r

    r = h.approve({"topic": "Email Marketing Best Practices for E-commerce"})
    assert r
    r = h.submit({"primary_keyword": "email marketing best practices", "search_volume": 6600, "kd": 55})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.4 Write outline")
    assert r
    r = h.submit({"outline": {"h1": "Email Marketing Best Practices: 15 Strategies That Drive Revenue", "sections": ["intro", "body"]}})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r

    r = h.submit({"section": "intro", "word_count": 380, "draft": "Email marketing delivers $36 for every $1 spent..."})
    assert r
    assert h.step == "2.2 Optimize for SEO"

    # Stop to wait for Google Search Console data refresh before optimizing
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Optimize for SEO"

    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Optimize for SEO"

    r = h.submit({"keywords_placed": ["email marketing best practices", "ecommerce email strategy"], "density": "1.0%", "gsc_impressions_baseline": 1200})
    assert r
    assert r.new_step == "2.3 Section quality check"
    assert h.step == "2.3 Section quality check"


def test_skip_a_section(harness_factory):
    """'SaaS pricing models' article: body section already written by domain expert, skip it."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro", "body", "conclusion"]},
    )
    r = h.start()
    assert r

    r = h.approve({"topic": "SaaS Pricing Models Explained"})
    assert r
    r = h.submit({"primary_keyword": "saas pricing models", "search_volume": 3200, "kd": 41})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.4 Write outline")
    assert r
    r = h.submit({"outline": {"sections": ["intro", "body (pricing model deep-dive)", "conclusion"]}})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r

    # Section 1 (intro): complete
    r = h.submit({"section": "intro", "word_count": 400, "draft": "Choosing the right pricing model can make or break your SaaS..."})
    assert r
    r = h.submit({"keywords_placed": ["saas pricing models"], "density": "1.2%"})
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r

    # Section 2 (body): skip -- already written by pricing consultant
    assert h.step == "2.1 Write section draft"
    r = h.skip("Body section pre-written by pricing consultant with real case studies")
    assert r
    assert r.new_step == "2.2 Optimize for SEO"
    assert h.step == "2.2 Optimize for SEO"
    r = h.skip("SEO already optimized by consultant who included target keywords")
    assert r
    assert r.new_step == "2.3 Section quality check"
    assert h.step == "2.3 Section quality check"
    r = h.submit_goto("2.0 Section loop")
    assert r

    # Section 3 (conclusion): complete
    assert h.step == "2.1 Write section draft"
    r = h.submit({"section": "conclusion", "word_count": 350, "draft": "The best SaaS pricing model depends on your growth stage..."})
    assert r
    r = h.submit({"keywords_placed": ["saas pricing strategy"], "density": "0.9%", "cta": "Free pricing audit template download"})
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r

    assert h.step == "3.1 Assemble full article"


def test_complete_then_reset_next_article(harness_factory):
    """Complete 'best CRM software' article, reset to start 'CRM implementation guide' next."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    r = h.start()
    assert r

    r = h.approve({"topic": "Best CRM Software for Small Business"})
    assert r
    r = h.submit({"primary_keyword": "best CRM for small business", "search_volume": 8100, "kd": 62})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.4 Write outline")
    assert r
    r = h.submit({"outline": {"h1": "11 Best CRM Software for Small Business (2025 Comparison)", "sections": ["intro"]}})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r
    r = h.submit({"section": "intro", "word_count": 450, "draft": "Finding the right CRM can save your sales team 5+ hours per week..."})
    assert r
    r = h.submit({"keywords_placed": ["best CRM for small business", "CRM software comparison"], "density": "1.1%"})
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r
    r = h.submit({"total_word_count": 450, "affiliate_links": 11, "schema": "ItemList"})
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
    assert h.step == "1.1 Choose topic"
    assert h.status == "waiting"


def test_back(harness_factory):
    """'GraphQL vs REST' article: after keyword research, go back to check if new Ahrefs data loaded."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    r = h.start()
    assert r

    r = h.approve({"topic": "GraphQL vs REST API: Which to Choose"})
    assert r
    assert r.new_step == "1.2 Keyword research"
    assert h.step == "1.2 Keyword research"

    r = h.submit({
        "primary_keyword": "graphql vs rest",
        "search_volume": 9900,
        "kd": 48,
        "note": "Ahrefs data might be stale, checking refresh",
    })
    assert r
    assert r.new_step == "1.3 Keyword review"
    assert h.step == "1.3 Keyword review"

    # Go back to keyword research to incorporate updated Ahrefs data
    r = h.back()
    assert r
    assert r.new_step == "1.2 Keyword research"
    assert h.step == "1.2 Keyword research"


def test_modify_yaml_add_section(harness_factory):
    """'AI writing tools' article: add proofreading step after client requests Grammarly/Hemingway pass on all sections."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    r = h.start()
    assert r

    r = h.approve({"topic": "Best AI Writing Tools for Content Marketers"})
    assert r
    r = h.submit({"primary_keyword": "ai writing tools", "search_volume": 12100, "kd": 64, "cpc": "$8.50"})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("1.4 Write outline")
    assert r
    r = h.submit({"outline": {"h1": "9 Best AI Writing Tools for Content Marketing (2025)", "sections": ["intro"]}})
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Section loop")
    assert r

    r = h.submit({"section": "intro", "word_count": 500, "draft": "AI writing tools have evolved from basic spinners to sophisticated assistants..."})
    assert r
    assert r.new_step == "2.2 Optimize for SEO"
    assert h.step == "2.2 Optimize for SEO"

    # Client requests proofreading step -- modify YAML
    modified_yaml = """\u540d\u79f0: Keyword-First Workflow
\u63cf\u8ff0: Modified with proofreading

\u6b65\u9aa4:
  - 1.1 Choose topic:
      \u7c7b\u578b: wait

  - 1.2 Keyword research

  - 1.3 Keyword review:
      \u7c7b\u578b: wait
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "keywords approved"
          \u53bb: 1.4 Write outline
        - \u53bb: 1.2 Keyword research

  - 1.4 Write outline

  - 1.5 Outline review:
      \u7c7b\u578b: wait
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "outline approved"
          \u53bb: 2.0 Section loop
        - \u53bb: 1.4 Write outline

  - 2.0 Section loop:
      \u904d\u5386: "sections"
      \u5b50\u6b65\u9aa4:
        - 2.1 Write section draft
        - 2.2 Optimize for SEO
        - 2.25 Proofread section
        - 2.3 Section quality check:
            \u4e0b\u4e00\u6b65:
              - \u5982\u679c: "section meets quality and SEO standards"
                \u53bb: 2.0 Section loop
              - \u53bb: 2.1 Write section draft

  - 3.1 Assemble full article

  - 3.2 Final review:
      \u7c7b\u578b: wait
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "article approved for publication"
          \u53bb: Done
        - \u53bb: 2.0 Section loop

  - Done:
      \u7c7b\u578b: terminate
"""
    h.reload_yaml(modified_yaml)

    r = h.submit({"keywords_placed": ["ai writing tools", "content marketing AI"], "density": "1.3%", "alt_tags_added": 2})
    assert r
    assert r.new_step == "2.25 Proofread section"
    assert h.step == "2.25 Proofread section"

    r = h.submit({"grammarly_score": 96, "hemingway_grade": 7, "passive_voice_pct": "4%", "issues_fixed": 3})
    assert r
    assert r.new_step == "2.3 Section quality check"
    assert h.step == "2.3 Section quality check"


# ===============================================================
# New multi-dimension tests
# ===============================================================

def test_data_accumulates_through_phases(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    h.start()
    h.approve({"topic": "SEO best practices"})
    data = h.state.data
    assert "1.1 Choose topic" in data
    assert data["1.1 Choose topic"]["topic"] == "SEO best practices"

    h.submit({"keywords": ["seo", "ranking"]})
    data = h.state.data
    assert "1.2 Keyword research" in data
    assert data["1.2 Keyword research"]["keywords"] == ["seo", "ranking"]


def test_data_accumulates_in_section_loop(harness_factory):
    """Data submitted during section loop persists."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro", "body"]},
    )
    _advance_to_section_loop(h)

    h.submit({"draft": "Introduction paragraph"})
    data = h.state.data
    assert "2.1 Write section draft" in data
    assert data["2.1 Write section draft"]["draft"] == "Introduction paragraph"


def test_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected actions."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    _advance_to_section_loop(h)
    _do_one_section(h)
    assert h.step == "3.1 Assemble full article"
    h.submit({})  # 3.1 -> 3.2
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "approve" in actions
    assert "terminate" in actions[-1]


def test_cross_executor_at_keyword_review(harness_factory):
    """Close executor at keyword review wait, reopen, state persists."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    h.start()
    h.approve({})  # 1.1 -> 1.2
    h.submit({})   # 1.2 -> 1.3
    assert h.step == "1.3 Keyword review"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "1.3 Keyword review"
    assert h.status == "waiting"


def test_cross_executor_in_section_loop(harness_factory):
    """Close executor mid-section loop, reopen, loop_state persists."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro", "body", "conclusion"]},
    )
    _advance_to_section_loop(h)

    _do_one_section(h)  # complete section 1
    h.submit({})  # 2.1 -> 2.2 (section 2)
    assert h.step == "2.2 Optimize for SEO"

    h.new_executor()

    assert h.step == "2.2 Optimize for SEO"
    loop_info = h.state.loop_state.get("2.0 Section loop")
    assert loop_info is not None
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_node_validates_section_draft(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    _advance_to_section_loop(h)

    h.register_node(
        "2.1 Write section draft",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("content") else "must include content",
        ),
    )

    r = h.submit({"notes": "todo"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"content": "Introduction to SEO..."})
    assert r
    assert r.new_step == "2.2 Optimize for SEO"


def test_node_archives_sections(harness_factory):
    """Archive node writes section data to SQLite table per iteration."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro", "body"]},
    )
    _advance_to_section_loop(h)

    h.register_node(
        "2.1 Write section draft",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"section_name": "string", "word_count": "string"}},
            archive={"table": "section_drafts"},
        ),
    )

    h.submit({"section_name": "intro", "word_count": "500"})
    h.submit({})  # 2.2
    h.submit_goto("2.0 Section loop")

    h.submit({"section_name": "body", "word_count": "1200"})

    rows = h.get_archived_rows("section_drafts")
    assert len(rows) == 2
    assert rows[0]["section_name"] == "intro"
    assert rows[1]["section_name"] == "body"


def test_submit_on_waiting_topic_fails(harness_factory):
    """Submit while topic wait step is waiting returns failure."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    h.start()
    assert h.step == "1.1 Choose topic"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    h.start()
    h.approve({})  # 1.1 -> 1.2
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    h.start()
    h.approve({"topic": "SEO"})
    h.submit({"keywords": ["seo"]})
    assert h.step == "1.3 Keyword review"

    h.save_checkpoint("at_keyword_review")

    h.approve()
    h.submit_goto("1.4 Write outline")
    assert h.step == "1.4 Write outline"

    restored = h.load_checkpoint("at_keyword_review")
    assert restored is not None
    assert restored.current_step == "1.3 Keyword review"


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    h.start()
    h.approve({})  # 1.1 -> 1.2
    assert h.step == "1.2 Keyword research"

    r = h.retry()
    assert r
    assert h.step == "1.2 Keyword research"
    assert h.status == "running"


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    h.start()
    h.approve({})
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )
    _advance_to_section_loop(h)
    _do_one_section(h)
    h.submit({})  # 3.1 -> 3.2
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p5-keyword-first.yaml",
        loop_data={"sections": ["intro"]},
    )

    for _ in range(3):
        h.start()
        h.approve({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Choose topic"
    assert h.status == "waiting"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p5-keyword-first.yaml", loop_data={"sections": ["intro"]})
    h.start()
    h.register_node(
        "1.1 Choose topic",
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
    h = harness_factory("p5-keyword-first.yaml", loop_data={"sections": ["intro"]})
    h.start()
    h.register_node(
        "1.1 Choose topic",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
