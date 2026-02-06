"""Systematic Literature Review workflow tests (p4-literature-review.yaml).

Tests the paper screening loop with include/exclude 2-way branching,
synthesis phase, and review wait with fallback to search.
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, EditPolicyPattern, NodeDefinition

# --- Helpers ---

def _advance_to_paper_loop(h):
    """Start -> submit through 1.1, 1.2, 1.3 -> arrive at 2.1 Screen paper."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 1.3
    h.submit({})  # 1.3 -> 2.1 (enters paper loop)
    assert h.step == "2.1 Screen paper"


def _do_include_paper(h):
    """At 2.1, screen and include paper (2.1 -> 2.2 -> 2.3 Extract data -> loop)."""
    h.submit({})  # 2.1 -> 2.2
    h.submit_goto("2.3 Extract data")  # include
    h.submit({})  # 2.3 -> loop header


def _do_exclude_paper(h):
    """At 2.1, screen and exclude paper (2.1 -> 2.2 -> loop header)."""
    h.submit({})  # 2.1 -> 2.2
    h.submit_goto("2.0 Paper loop")  # exclude


def _complete_to_done(h):
    """From 3.1, complete synthesis -> review -> write report -> Done."""
    h.submit({})  # 3.1 -> 3.2
    assert h.step == "3.2 Review"
    assert h.status == "waiting"
    h.approve()
    h.submit_goto("3.3 Write report")
    h.submit({})  # 3.3 -> Done
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Existing tests (unchanged)
# ===============================================================

def test_screen_15_papers_include_8(harness_factory):
    """Screen 15 papers on caffeine and cognitive performance: include 8 RCTs, exclude 7 observational studies."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": [f"p{i}" for i in range(1, 16)]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define research question"
    assert h.status == "running"

    r = h.submit({
        "question": "Does caffeine intake (200-400mg/day) improve cognitive performance in adults aged 18-65?",
        "pico": {
            "population": "Healthy adults 18-65",
            "intervention": "Caffeine 200-400mg/day",
            "comparison": "Placebo or no caffeine",
            "outcome": "Cognitive performance (reaction time, memory, attention)",
        },
        "inclusion_criteria": ["RCT or quasi-experimental", "English language", "Published 2015-2024", "Peer-reviewed"],
        "exclusion_criteria": ["Case studies", "Animal models", "Pediatric populations", "Conference abstracts only"],
    })
    assert r
    assert r.new_step == "1.2 Search databases"
    assert h.step == "1.2 Search databases"
    assert h.status == "running"

    r = h.submit({
        "databases": ["PubMed", "PsycINFO", "Cochrane Library", "Web of Science", "Scopus"],
        "search_string": '("caffeine" OR "coffee" OR "1,3,7-trimethylxanthine") AND ("cognitive performance" OR "cognition" OR "attention" OR "memory" OR "reaction time")',
        "date_range": "2015-01-01 to 2024-12-31",
        "total_hits": {"PubMed": 342, "PsycINFO": 189, "Cochrane": 67, "Web of Science": 412, "Scopus": 298},
        "after_dedup": 487,
    })
    assert r
    assert r.new_step == "1.3 Collect papers"
    assert h.step == "1.3 Collect papers"

    r = h.submit({
        "papers_collected": 487,
        "after_title_abstract_screen": 15,
        "export_format": "RIS",
        "reference_manager": "Zotero",
    })
    assert r
    assert r.new_step == "2.1 Screen paper"
    assert h.step == "2.1 Screen paper"

    paper_titles = [
        "Double-blind RCT of 200mg caffeine on working memory in university students",
        "Caffeine and sustained attention: a crossover trial in shift workers",
        "Effects of espresso consumption on Stroop task performance",
        "Dose-response relationship of caffeine on reaction time: RCT with 100/200/400mg arms",
        "Caffeine withdrawal and cognitive decline: a 4-week placebo-controlled study",
        "Green tea catechins and caffeine synergy on executive function",
        "Acute caffeine administration improves vigilance in sleep-deprived adults",
        "L-theanine and caffeine combination effects on attention: double-blind RCT",
        "Observational study: coffee habits and dementia risk in Finnish cohort",
        "Cross-sectional survey of caffeine use among college students",
        "Caffeine and anxiety: a retrospective chart review",
        "Ecological momentary assessment of caffeine intake and mood",
        "Qualitative interviews on caffeine perceptions among athletes",
        "Coffee consumption patterns: a population-based descriptive study",
        "Narrative review of caffeine and brain health (no original data)",
    ]

    included = 0
    for i in range(15):
        assert h.step == "2.1 Screen paper"
        r = h.submit({
            "paper_id": f"p{i+1}",
            "title": paper_titles[i],
            "year": 2019 + (i % 6),
            "journal": ["J Psychopharmacol", "Psychopharmacology", "Nutrients", "Sleep", "Appetite"][i % 5],
        })
        assert r
        assert r.new_step == "2.2 Include or exclude"
        assert h.step == "2.2 Include or exclude"

        if i < 8:
            # Include: meets criteria -> extract data -> next paper
            r = h.submit_goto("2.3 Extract data")
            assert r
            assert h.step == "2.3 Extract data"
            r = h.submit({
                "study_design": "RCT" if i != 5 else "Crossover RCT",
                "sample_size": [48, 72, 36, 120, 60, 44, 80, 56][i],
                "caffeine_dose_mg": [200, 200, 150, 400, 0, 250, 200, 200][i],
                "outcome_measures": ["working memory", "sustained attention", "Stroop", "reaction time", "withdrawal", "executive function", "vigilance", "attention"][i],
                "effect_size_cohens_d": [0.45, 0.62, 0.38, 0.71, -0.33, 0.55, 0.68, 0.41][i],
                "risk_of_bias": ["low", "low", "moderate", "low", "low", "moderate", "low", "low"][i],
            })
            assert r
            included += 1
        else:
            # Exclude: skip to next iteration
            r = h.submit_goto("2.0 Paper loop")
            assert r

        if i < 14:
            assert h.step == "2.1 Screen paper"

    assert included == 8
    assert h.step == "3.1 Synthesize findings"

    r = h.submit({
        "synthesis_method": "Narrative synthesis with vote counting",
        "included_studies": 8,
        "pooled_effect_size": 0.49,
        "heterogeneity_I2": "62%",
        "key_finding": "Moderate evidence that 200-400mg caffeine improves reaction time and sustained attention with pooled Cohen's d = 0.49",
        "certainty_of_evidence": "Moderate (GRADE)",
        "limitations": ["High heterogeneity in outcome measures", "Most studies short-duration (<4 weeks)", "Publication bias suspected"],
    })
    assert r
    assert r.new_step == "3.2 Review"
    assert h.step == "3.2 Review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first (sets running, submit({}) -> needs judgment), then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("3.3 Write report")
    assert r
    assert r.new_step == "3.3 Write report"
    assert h.step == "3.3 Write report"

    r = h.submit({
        "title": "Caffeine and Cognitive Performance in Adults: A Systematic Review",
        "word_count": 8500,
        "sections": ["Abstract", "Introduction", "Methods", "Results", "Discussion", "Conclusion"],
        "prisma_compliant": True,
        "tables": ["PRISMA flow diagram", "Study characteristics", "Risk of bias summary", "Forest plot data"],
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_many_exclusions(harness_factory):
    """Screen 5 papers on microplastics in drinking water: only 1 peer-reviewed field study meets criteria."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["a", "b", "c", "d", "e"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define research question"

    # Advance to paper loop
    r = h.submit({
        "question": "What is the concentration of microplastics in municipal drinking water systems?",
        "inclusion_criteria": ["Peer-reviewed field study", "Municipal tap water sampling", "Published 2020-2024"],
    })
    assert r
    r = h.submit({
        "databases": ["PubMed", "Environmental Science & Technology"],
        "total_hits": 83,
    })
    assert r
    r = h.submit({"papers_collected": 5, "screening_method": "Full-text review"})
    assert r

    for i in range(5):
        assert h.step == "2.1 Screen paper"
        r = h.submit({
            "paper_id": ["a", "b", "c", "d", "e"][i],
            "title": [
                "Microplastic detection methods in spiked water samples",
                "Microplastic contamination in commercial bottled water brands",
                "Nationwide survey of microplastic concentrations in US tap water",
                "Polymer identification in urban water supplies (2018)",
                "Preliminary findings on nanoplastics in treated water (SETAC proceedings)",
            ][i],
        })
        assert r
        assert r.new_step == "2.2 Include or exclude"
        assert h.step == "2.2 Include or exclude"

        if i == 2:
            # Only include paper c
            r = h.submit_goto("2.3 Extract data")
            assert r
            assert h.step == "2.3 Extract data"
            r = h.submit({
                "sample_size": 159,
                "locations": "37 US cities",
                "mean_concentration": "5.45 particles/L",
                "dominant_polymer": "Polyethylene (PE)",
            })
            assert r
        else:
            r = h.submit_goto("2.0 Paper loop")
            assert r

        if i < 4:
            assert h.step == "2.1 Screen paper"

    assert h.step == "3.1 Synthesize findings"


def test_review_needs_more_searching(harness_factory):
    """Reviewer flags gaps in SSRI efficacy review: missing EMBASE results, need to expand search."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    r = h.start()
    assert r

    # Complete first pass
    r = h.submit({
        "question": "Are SSRIs more effective than SNRIs for generalized anxiety disorder?",
    })
    assert r
    r = h.submit({
        "databases": ["PubMed", "Cochrane"],
        "note": "Forgot to include EMBASE",
    })
    assert r
    r = h.submit({"papers_collected": 1})
    assert r
    r = h.submit({"title": "Sertraline vs venlafaxine for GAD: 12-week RCT"})
    assert r
    r = h.submit_goto("2.3 Extract data")
    assert r
    r = h.submit({
        "sample_size": 180,
        "primary_outcome": "HAM-A score reduction",
        "result": "No significant difference (p=0.12)",
    })
    assert r

    assert h.step == "3.1 Synthesize findings"
    r = h.submit({
        "finding": "Insufficient evidence from single study to draw conclusions",
        "reviewer_note": "Only 1 study found - likely missing relevant literature",
    })
    assert r
    assert r.new_step == "3.2 Review"
    assert h.step == "3.2 Review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("1.2 Search databases")
    assert r
    assert r.new_step == "1.2 Search databases"
    assert h.step == "1.2 Search databases"
    assert h.status == "running"


def test_empty_paper_list(harness_factory):
    """Highly specific research question on CRISPR-Cas13 for prion diseases yields zero results."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": []},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define research question"

    r = h.submit({
        "question": "Can CRISPR-Cas13 RNA editing treat prion diseases in human clinical trials?",
        "note": "Extremely niche intersection of two cutting-edge fields",
    })
    assert r
    r = h.submit({
        "databases": ["PubMed", "ClinicalTrials.gov", "bioRxiv"],
        "total_hits": 0,
        "note": "No studies combining CRISPR-Cas13 and prion disease treatment found",
    })
    assert r
    r = h.submit({
        "papers_collected": 0,
        "recommendation": "Consider broadening to CRISPR-Cas9 or non-clinical prion research",
    })
    assert r

    # Loop exits immediately with empty list
    assert h.step == "3.1 Synthesize findings"
    assert h.status == "running"


def test_skip_a_paper(harness_factory):
    """Review papers on gut microbiome and depression: skip duplicate from co-author group."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1", "p2", "p3"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "question": "Does gut microbiome composition correlate with major depressive disorder severity?",
    })
    assert r
    r = h.submit({
        "databases": ["PubMed", "MEDLINE"],
        "search_string": '"gut microbiome" AND "depression" AND "severity"',
    })
    assert r
    r = h.submit({"papers_collected": 3})
    assert r

    # Paper 1: include
    r = h.submit({
        "title": "Altered Firmicutes/Bacteroidetes ratio in treatment-resistant depression",
        "authors": "Zhang et al.",
        "journal": "Nature Microbiology",
        "year": 2023,
    })
    assert r
    r = h.submit_goto("2.3 Extract data")
    assert r
    r = h.submit({
        "sample_size": 211,
        "key_finding": "Significantly reduced Lactobacillus in severe MDD (p<0.001)",
        "effect_size": "r=0.42",
    })
    assert r

    # Paper 2: skip screening -- same dataset published by co-author group
    assert h.step == "2.1 Screen paper"
    r = h.skip("Already reviewed this paper")
    assert r
    assert r.new_step == "2.2 Include or exclude"
    assert h.step == "2.2 Include or exclude"
    r = h.submit_goto("2.0 Paper loop")
    assert r

    # Paper 3: include
    assert h.step == "2.1 Screen paper"
    r = h.submit({
        "title": "Fecal microbiota transplant as adjunctive therapy for MDD: pilot RCT",
        "authors": "Kowalski et al.",
        "journal": "Translational Psychiatry",
        "year": 2024,
    })
    assert r
    r = h.submit_goto("2.3 Extract data")
    assert r
    r = h.submit({
        "sample_size": 40,
        "key_finding": "FMT group showed 35% greater HAM-D reduction at 8 weeks",
    })
    assert r

    assert h.step == "3.1 Synthesize findings"


def test_stop_then_resume(harness_factory):
    """Stop mid-screening of vitamin D meta-analysis for weekend break, resume Monday."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1", "p2"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "question": "Does vitamin D supplementation reduce all-cause mortality in adults over 50?",
    })
    assert r
    r = h.submit({
        "databases": ["PubMed", "Cochrane", "EMBASE"],
        "total_hits": 156,
    })
    assert r
    r = h.submit({"papers_collected": 2, "screening_phase": "full-text"})
    assert r

    assert h.step == "2.1 Screen paper"

    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.1 Screen paper"

    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.1 Screen paper"

    # Continue normally
    r = h.submit({
        "title": "Vitamin D3 at 4000 IU/day and mortality in community-dwelling elderly: the VITAL sub-study",
        "journal": "BMJ",
        "year": 2022,
    })
    assert r
    assert r.new_step == "2.2 Include or exclude"
    assert h.step == "2.2 Include or exclude"


def test_complete_then_reset_new_topic(harness_factory):
    """Complete review on telomere length and aging, reset to start new review on epigenetic clocks."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    r = h.start()
    assert r

    # Fast path through
    r = h.submit({"question": "Does telomere length predict biological aging rate?"})
    assert r
    r = h.submit({"databases": ["PubMed", "Scopus"], "total_hits": 89})
    assert r
    r = h.submit({"papers_collected": 1})
    assert r
    r = h.submit({"title": "Telomere attrition and age-related disease: Mendelian randomization analysis"})
    assert r
    r = h.submit_goto("2.3 Extract data")
    assert r
    r = h.submit({"sample_size": 472000, "method": "Mendelian randomization", "finding": "Causal link OR=1.08 per SD shorter telomeres"})
    assert r
    r = h.submit({"synthesis": "Strong genetic evidence for causal role of telomere length in aging"})
    assert r
    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("3.3 Write report")
    assert r
    r = h.submit({"title": "Telomere Length as a Biomarker of Biological Aging: A Systematic Review", "word_count": 6200})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define research question"
    assert h.status == "running"


def test_goto_synthesis(harness_factory):
    """Screening already done offline in Covidence -- jump to synthesizing 12 included studies on sleep hygiene interventions."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define research question"

    r = h.goto("3.1 Synthesize findings")
    assert r
    assert r.new_step == "3.1 Synthesize findings"
    assert h.step == "3.1 Synthesize findings"
    assert h.status == "running"

    r = h.submit({
        "studies_included": 12,
        "method": "Random-effects meta-analysis",
        "pooled_effect": "Sleep onset latency reduced by 14.2 minutes (95% CI: 8.7-19.7)",
        "subgroup_analysis": {
            "CBT-I": "18.5 min reduction",
            "sleep restriction": "12.1 min reduction",
            "stimulus control": "11.8 min reduction",
        },
    })
    assert r
    assert r.new_step == "3.2 Review"
    assert h.step == "3.2 Review"
    assert h.status == "waiting"


def test_modify_yaml_add_search_engine(harness_factory):
    """Hot-reload YAML to add a search engine selection step."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    r = h.start()
    assert r

    r = h.submit({})
    assert r
    assert r.new_step == "1.2 Search databases"
    assert h.step == "1.2 Search databases"

    modified_yaml = """\u540d\u79f0: Systematic Literature Review
\u63cf\u8ff0: Modified with search engine selection

\u6b65\u9aa4:
  - 1.1 Define research question

  - 1.15 Select search engines:
      \u4e0b\u4e00\u6b65: 1.2 Search databases

  - 1.2 Search databases

  - 1.3 Collect papers

  - 2.0 Paper loop:
      \u904d\u5386: "papers"
      \u5b50\u6b65\u9aa4:
        - 2.1 Screen paper
        - 2.2 Include or exclude:
            \u4e0b\u4e00\u6b65:
              - \u5982\u679c: "paper meets inclusion criteria"
                \u53bb: 2.3 Extract data
              - \u53bb: 2.0 Paper loop
        - 2.3 Extract data

  - 3.1 Synthesize findings

  - 3.2 Review:
      \u7c7b\u578b: wait
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "review is satisfactory"
          \u53bb: 3.3 Write report
        - \u53bb: 1.2 Search databases

  - 3.3 Write report

  - Done:
      \u7c7b\u578b: terminate
"""
    h.reload_yaml(modified_yaml)

    r = h.goto("1.15 Select search engines")
    assert r
    assert r.new_step == "1.15 Select search engines"
    assert h.step == "1.15 Select search engines"
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert r.new_step == "1.2 Search databases"
    assert h.step == "1.2 Search databases"


def test_back(harness_factory):
    """Use back to return to previous step."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    r = h.start()
    assert r

    r = h.submit({})
    assert r
    assert r.new_step == "1.2 Search databases"
    assert h.step == "1.2 Search databases"

    r = h.submit({})
    assert r
    assert r.new_step == "1.3 Collect papers"
    assert h.step == "1.3 Collect papers"

    r = h.back()
    assert r
    assert r.new_step == "1.2 Search databases"
    assert h.step == "1.2 Search databases"

    # Continue forward again
    r = h.submit({})
    assert r
    assert r.new_step == "1.3 Collect papers"
    assert h.step == "1.3 Collect papers"

    r = h.submit({})
    assert r
    assert h.step == "2.1 Screen paper"


# ===============================================================
# New multi-dimension tests
# ===============================================================

def test_data_accumulates_through_phases(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    h.start()

    h.submit({"question": "effects of caffeine"})
    data = h.state.data
    assert "1.1 Define research question" in data
    assert data["1.1 Define research question"]["question"] == "effects of caffeine"

    h.submit({"databases": ["PubMed", "Scopus"]})
    data = h.state.data
    assert "1.2 Search databases" in data

    h.submit({"papers_found": 42})
    data = h.state.data
    assert "1.3 Collect papers" in data
    assert data["1.3 Collect papers"]["papers_found"] == 42


def test_data_accumulates_in_loop(harness_factory):
    """Data submitted during loop iterations persists in state.data."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1", "p2"]},
    )
    _advance_to_paper_loop(h)

    h.submit({"screening": "relevant"})
    data = h.state.data
    assert "2.1 Screen paper" in data
    assert data["2.1 Screen paper"]["screening"] == "relevant"


def test_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected actions."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    _advance_to_paper_loop(h)
    _do_include_paper(h)
    assert h.step == "3.1 Synthesize findings"
    _complete_to_done(h)

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "approve" in actions
    assert "terminate" in actions[-1]


def test_cross_executor_at_screening(harness_factory):
    """Close executor during screening, reopen, state persists."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1", "p2"]},
    )
    _advance_to_paper_loop(h)

    h.submit({})  # 2.1 -> 2.2
    assert h.step == "2.2 Include or exclude"

    h.new_executor()

    assert h.step == "2.2 Include or exclude"
    assert h.status == "running"

    # Continue from where we left off
    r = h.submit_goto("2.3 Extract data")
    assert r
    assert h.step == "2.3 Extract data"


def test_cross_executor_at_review(harness_factory):
    """Close executor at review wait step, reopen, state persists."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    _advance_to_paper_loop(h)
    _do_include_paper(h)
    assert h.step == "3.1 Synthesize findings"
    h.submit({})  # 3.1 -> 3.2
    assert h.step == "3.2 Review"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "3.2 Review"
    assert h.status == "waiting"


def test_cross_executor_preserves_loop_state(harness_factory):
    """Close executor mid-loop, reopen, loop_state preserved."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1", "p2", "p3"]},
    )
    _advance_to_paper_loop(h)

    # Complete paper 1
    _do_include_paper(h)
    assert h.step == "2.1 Screen paper"

    h.new_executor()

    assert h.step == "2.1 Screen paper"
    loop_info = h.state.loop_state.get("2.0 Paper loop")
    assert loop_info is not None
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_node_validates_screen_paper(harness_factory):
    """Validate node rejects bad screening data, accepts good data."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    _advance_to_paper_loop(h)

    h.register_node(
        "2.1 Screen paper",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("relevance") else "must include relevance score",
        ),
    )

    r = h.submit({"notes": "interesting paper"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"relevance": "high"})
    assert r
    assert r.new_step == "2.2 Include or exclude"


def test_node_archives_extracted_data(harness_factory):
    """Archive node writes extracted paper data to SQLite table."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1", "p2"]},
    )
    _advance_to_paper_loop(h)

    h.register_node(
        "2.3 Extract data",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"title": "string", "year": "string"}},
            archive={"table": "extracted_papers"},
        ),
    )

    # Paper 1: include with data
    h.submit({})  # 2.1 -> 2.2
    h.submit_goto("2.3 Extract data")
    h.submit({"title": "Paper One", "year": "2024"})

    # Paper 2: include with data
    h.submit({})  # 2.1 -> 2.2
    h.submit_goto("2.3 Extract data")
    h.submit({"title": "Paper Two", "year": "2025"})

    rows = h.get_archived_rows("extracted_papers")
    assert len(rows) == 2
    assert rows[0]["title"] == "Paper One"
    assert rows[1]["title"] == "Paper Two"


def test_submit_on_waiting_review_fails(harness_factory):
    """Submit while review step is waiting returns failure."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    _advance_to_paper_loop(h)
    _do_include_paper(h)
    h.submit({})  # 3.1 -> 3.2
    assert h.step == "3.2 Review"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    _advance_to_paper_loop(h)

    h.save_checkpoint("at_screening")

    # Continue working
    _do_include_paper(h)
    assert h.step == "3.1 Synthesize findings"

    # Load checkpoint
    restored = h.load_checkpoint("at_screening")
    assert restored is not None
    assert restored.current_step == "2.1 Screen paper"


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    h.start()
    h.submit({})  # 1.1 -> 1.2
    assert h.step == "1.2 Search databases"

    r = h.retry()
    assert r
    assert h.step == "1.2 Search databases"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
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
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    h.start()
    h.goto("3.3 Write report")
    h.submit({})
    assert h.step == "Done"
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define research question"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    _advance_to_paper_loop(h)
    assert h.step == "2.1 Screen paper"

    h.register_node(
        "2.1 Screen paper",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nScreen the paper for relevance.\n\n## Steps\n1. Read abstract\n2. Check inclusion criteria",
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
        "p4-literature-review.yaml",
        loop_data={"papers": ["p1"]},
    )
    h.start()
    assert h.step == "1.1 Define research question"

    h.register_node(
        "1.1 Define research question",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="block",
                patterns=[
                    EditPolicyPattern(glob="notes/**", policy="silent"),
                ],
            ),
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["edit_policy"] is not None
    assert status["node"]["edit_policy"]["default"] == "block"
