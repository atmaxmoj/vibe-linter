"""Test scenarios for Atomic Design workflow (p2-atomic.yaml).

Tests the Atomic Design workflow including:
- Nested loops (level loop containing element loop)
- Planning phase (define design system levels)
- Integration phase with 2-way branching
- State transitions, gotos, stops/resumes, and hot-reload

Workflow structure:
  1.1 Define design system levels
  2.0 Level loop (iterate: levels)
    2.0.1 Element loop (iterate: current_level_elements)
      2.1 Implement element
      2.2 Test element
      2.3 Element check (LLM 2-way: correct->2.0.1, else->2.1)
  3.1 Compose final pages
  3.2 Integration testing (LLM 2-way: pass->Done, else->2.0)
  Done (terminate)

Dimensions tested per scenario:
  - State machine transitions (happy path)
  - Data accumulation (submit data persists in state.data)
  - History audit trail (action sequence in get_history)
  - Cross-executor recovery (close + new_executor + resume)
  - Node validation (validate node rejects bad data)
  - Node archival (archive node writes to SQLite)
  - Error boundaries (wrong-state operations fail gracefully)
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# --- Helpers ---

def _walk_to_inner_loop(h):
    """Start -> submit 1.1 -> arrive at 2.1 (running) in inner loop."""
    h.start()
    h.submit({"levels": "defined"})
    assert h.step == "2.1 Implement element"
    assert h.status == "running"


def _do_one_element(h):
    """Complete one implement-test-check cycle ending at element check."""
    h.submit({"element": "impl"})
    h.submit({"tests": "pass"})
    assert h.step == "2.3 Element check"


# ===============================================================
# Scenario 1: Three levels, three elements each
# ===============================================================

def test_three_levels_three_elements(harness_factory):
    """Build SaaS dashboard design system: Atoms (Button, Input, Badge), Molecules (SearchField, StatCard, UserBadge), Organisms (Navbar, DataPanel, FilterBar)."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={
            "levels": ["atoms", "molecules", "organisms"],
            "current_level_elements": ["element_1", "element_2", "element_3"],
        },
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define design system levels"
    assert h.status == "running"

    # Define the 5 Atomic Design levels for a SaaS dashboard
    r = h.submit({
        "design_system": "Acme Dashboard DS",
        "levels": {
            "atoms": ["Button", "Input", "Badge"],
            "molecules": ["SearchField", "StatCard", "UserBadge"],
            "organisms": ["Navbar", "DataPanel", "FilterBar"],
        },
        "tooling": "Tailwind CSS + CVA (class-variance-authority) for variant management",
    })
    assert r
    assert r.new_step == "2.1 Implement element"
    assert h.step == "2.1 Implement element"
    assert h.status == "running"

    # ── Level 1: Atoms ──
    # Atom 1: Button with variants (primary, secondary, ghost, destructive)
    r = h.submit({
        "element": "Button",
        "file": "src/atoms/Button/Button.tsx",
        "variants": ["primary", "secondary", "ghost", "destructive"],
        "sizes": ["sm", "md", "lg"],
        "implementation": "CVA with Tailwind classes, forwardRef, polymorphic 'as' prop, loading spinner state",
    })
    assert r
    assert r.new_step == "2.2 Test element"
    assert h.step == "2.2 Test element"
    assert h.status == "running"

    r = h.submit({
        "test_file": "src/atoms/Button/Button.test.tsx",
        "tests": ["renders all 4 variants with correct colors", "handles click events", "shows spinner when loading", "renders as <a> when as='a' passed"],
        "coverage": "98%",
    })
    assert r
    assert r.new_step == "2.3 Element check"
    assert h.step == "2.3 Element check"
    assert h.status == "running"

    r = h.submit_goto("2.0.1 Element loop")
    assert r
    assert r.new_step == "2.1 Implement element"
    assert h.step == "2.1 Implement element"
    assert h.status == "running"

    # Atom 2: Input, Atom 3: Badge
    for _ in range(2):
        r = h.submit()
        assert r
        r = h.submit()
        assert r
        r = h.submit_goto("2.0.1 Element loop")
        assert r

    # Exit inner loop, back to outer loop -> Level 2
    assert h.step == "2.1 Implement element"

    # ── Level 2: Molecules ── (SearchField, StatCard, UserBadge)
    for _ in range(3):
        r = h.submit()
        assert r
        r = h.submit()
        assert r
        r = h.submit_goto("2.0.1 Element loop")
        assert r

    # ── Level 3: Organisms ── (Navbar, DataPanel, FilterBar)
    for _ in range(3):
        r = h.submit()
        assert r
        r = h.submit()
        assert r
        r = h.submit_goto("2.0.1 Element loop")
        assert r

    # Exit both loops, go to page composition
    assert h.step == "3.1 Compose final pages"
    assert h.status == "running"

    r = h.submit({
        "pages_composed": ["DashboardPage", "AnalyticsPage", "SettingsPage"],
        "layout": "Navbar organism top, FilterBar left sidebar, DataPanel main content area with StatCard grid",
        "routing": "React Router v6 with lazy-loaded page components",
    })
    assert r
    assert r.new_step == "3.2 Integration testing"
    assert h.step == "3.2 Integration testing"
    assert h.status == "running"

    # Integration passes: all atoms compose correctly into molecules and organisms
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["btn"]},
    )
    h.start()

    h.submit({"levels": "atoms only"})
    data = h.state.data
    assert "1.1 Define design system levels" in data
    assert data["1.1 Define design system levels"]["levels"] == "atoms only"

    h.submit({"element": "button"})
    data = h.state.data
    assert "2.1 Implement element" in data
    assert data["2.1 Implement element"]["element"] == "button"

    h.submit({"tests": "all pass"})
    data = h.state.data
    assert "2.2 Test element" in data
    assert data["2.2 Test element"]["tests"] == "all pass"


def test_s1_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["e1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0.1 Element loop")
    assert h.step == "3.1 Compose final pages"
    h.submit({})
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_s1_cross_executor_at_planning(harness_factory):
    """Close executor at planning phase, reopen, continue."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["btn"]},
    )
    h.start()
    assert h.step == "1.1 Define design system levels"

    h.new_executor()

    assert h.step == "1.1 Define design system levels"
    assert h.status == "running"

    r = h.submit({"levels": "defined"})
    assert r
    assert h.step == "2.1 Implement element"


def test_s1_cross_executor_at_inner_loop(harness_factory):
    """Close executor mid-inner-loop, reopen, both loop states preserved."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms", "molecules"], "current_level_elements": ["a", "b"]},
    )
    _walk_to_inner_loop(h)

    h.submit({"element": "a_impl"})
    assert h.step == "2.2 Test element"

    h.new_executor()

    assert h.step == "2.2 Test element"
    assert h.status == "running"
    inner_info = h.state.loop_state.get("2.0.1 Element loop")
    assert inner_info is not None
    assert inner_info["i"] == 0
    outer_info = h.state.loop_state.get("2.0 Level loop")
    assert outer_info is not None
    assert outer_info["i"] == 0


def test_s1_node_validates_element(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["btn"]},
    )
    _walk_to_inner_loop(h)

    h.register_node(
        "2.1 Implement element",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("element") else "must include element name",
        ),
    )

    # Bad data
    r = h.submit({"notes": "forgot"})
    assert not r
    assert "rejected" in r.message.lower()

    # Good data
    r = h.submit({"element": "button"})
    assert r
    assert r.new_step == "2.2 Test element"


def test_s1_node_archives_elements(harness_factory):
    """Archive node writes submitted data to SQLite table."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["a", "b"]},
    )
    _walk_to_inner_loop(h)

    h.register_node(
        "2.1 Implement element",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"elem_name": "string", "level": "string"}},
            archive={"table": "atomic_elements"},
        ),
    )

    h.submit({"elem_name": "button", "level": "atoms"})
    h.submit({})
    h.submit_goto("2.0.1 Element loop")
    h.submit({"elem_name": "input", "level": "atoms"})

    rows = h.get_archived_rows("atomic_elements")
    assert len(rows) == 2
    assert rows[0]["elem_name"] == "button"
    assert rows[1]["elem_name"] == "input"


# ===============================================================
# Scenario 2: Inner element repeated fix
# ===============================================================

def test_inner_element_repeated_fix(harness_factory):
    """TextInput atom fails visual check 4 times: placeholder color, focus ring, error state border, disabled opacity."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["text_input"]},
    )
    r = h.start()
    assert r

    # Go through planning to properly initialize both loops
    r = h.submit({
        "levels": {"atoms": ["TextInput"]},
        "design_system": "Acme DS - building input atom to match Figma spec",
    })
    assert r
    assert h.step == "2.1 Implement element"
    assert h.status == "running"

    # Initial implementation
    r = h.submit({
        "element": "TextInput",
        "file": "src/atoms/TextInput/TextInput.tsx",
        "implementation": "Controlled input with label, helper text, error message, prefix/suffix icon slots",
    })
    assert r
    r = h.submit({
        "tests": ["renders with label", "shows error message", "calls onChange", "supports prefix icon"],
    })
    assert r
    assert h.step == "2.3 Element check"

    # Round 1: placeholder text color too light (#ccc vs Figma spec #888)
    r = h.submit_goto("2.1 Implement element")
    assert r
    assert r.new_step == "2.1 Implement element"
    assert h.step == "2.1 Implement element"

    r = h.submit({
        "element": "TextInput",
        "fix": "Changed placeholder color from #ccc to var(--color-text-placeholder) which maps to #888",
        "attempt": 1,
    })
    assert r
    r = h.submit()
    assert r
    assert h.step == "2.3 Element check"

    # Round 2: focus ring uses box-shadow instead of outline (fails forced-colors mode)
    r = h.submit_goto("2.1 Implement element")
    assert r
    r = h.submit({
        "element": "TextInput",
        "fix": "Replaced box-shadow focus ring with outline: 2px solid var(--color-focus) for Windows high-contrast mode support",
        "attempt": 2,
    })
    assert r
    r = h.submit()
    assert r
    assert h.step == "2.3 Element check"

    # Round 3: error state border is red but needs to be 2px not 1px per spec
    r = h.submit_goto("2.1 Implement element")
    assert r
    r = h.submit({
        "element": "TextInput",
        "fix": "Error state: border-width 1px -> 2px, added aria-invalid='true' and aria-describedby linking to error message",
        "attempt": 3,
    })
    assert r
    r = h.submit()
    assert r
    assert h.step == "2.3 Element check"

    # Round 4: disabled state opacity matches Figma spec, all visual checks pass
    r = h.submit_goto("2.1 Implement element")
    assert r
    r = h.submit({
        "element": "TextInput",
        "fix": "Disabled opacity: 0.5 -> 0.38 to match Material-like spec, cursor: not-allowed, removed pointer-events",
        "attempt": 4,
        "visual_qa": "Pixel-perfect match with Figma for all 5 states: default, hover, focus, error, disabled",
    })
    assert r
    r = h.submit()
    assert r
    assert h.step == "2.3 Element check"

    # Passes this time
    r = h.submit_goto("2.0.1 Element loop")
    assert r
    assert r.new_step == "3.1 Compose final pages"
    assert h.step == "3.1 Compose final pages"
    assert h.status == "running"


def test_s2_data_has_all_attempts(harness_factory):
    """All fix attempts store data (last wins per step key)."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.submit({})
    h.goto("2.1 Implement element")

    for i in range(4):
        h.submit({"element": f"attempt_{i}"})
        if h.step != "2.1 Implement element":
            h.goto("2.1 Implement element")

    data = h.state.data
    assert "2.1 Implement element" in data


def test_s2_cross_executor_mid_retry(harness_factory):
    """Close executor after retries, reopen, continue from same step."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.submit({})
    # At 2.1
    h.submit({})
    h.submit({})
    assert h.step == "2.3 Element check"

    for _ in range(2):
        h.submit_goto("2.1 Implement element")
        h.submit({})
        h.submit({})
    assert h.step == "2.3 Element check"

    h.new_executor()
    assert h.step == "2.3 Element check"
    assert h.status == "running"


# ===============================================================
# Scenario 3: Empty inner loop
# ===============================================================

def test_empty_inner_loop(harness_factory):
    """Atoms level defined but no elements to implement yet: team is still finalizing the Figma audit."""
    h = harness_factory(
        "p2-atomic.yaml", loop_data={"levels": ["atoms"], "current_level_elements": []}
    )
    r = h.start()
    assert r

    # Planning: atoms level exists but Figma audit identified no new atoms needed (all exist in upstream library)
    r = h.submit({
        "levels": {"atoms": []},
        "reason": "Figma audit complete: all required atoms (Button, Input, Badge, Icon) already exist in @acme/primitives. No new atoms to build.",
    })
    assert r

    # Inner loop should exit immediately - no atoms to implement
    assert h.step == "3.1 Compose final pages"
    assert h.status == "running"


# ===============================================================
# Scenario 4: Empty outer loop
# ===============================================================

def test_empty_outer_loop(harness_factory):
    """Micro-frontend recomposition: no new design system levels needed, jump straight to page assembly."""
    h = harness_factory(
        "p2-atomic.yaml", loop_data={"levels": [], "current_level_elements": ["e1"]}
    )
    r = h.start()
    assert r

    # Planning: existing design system covers all levels, this ticket is just re-composing pages with existing components
    r = h.submit({
        "levels": [],
        "reason": "Design system v3.2 already has complete atom/molecule/organism coverage. This ticket only restructures page layouts for the new IA.",
    })
    assert r

    # Outer loop should exit immediately - all levels already built
    assert h.step == "3.1 Compose final pages"
    assert h.status == "running"


# ===============================================================
# Scenario 5: Integration atom problem back
# ===============================================================

def test_integration_atom_problem_back(harness_factory):
    """Integration test reveals Button atom has wrong border-radius when composed in CardHeader organism."""
    h = harness_factory(
        "p2-atomic.yaml", loop_data={"levels": ["atoms"], "current_level_elements": ["button"]}
    )
    r = h.start()
    assert r

    # Jump to integration testing - pages already composed
    r = h.goto("3.2 Integration testing")
    assert r
    assert r.new_step == "3.2 Integration testing"
    assert h.step == "3.2 Integration testing"
    assert h.status == "running"

    # Integration fails: Button atom renders with rounded-full in CardHeader but should be rounded-md
    r = h.submit_goto("2.0 Level loop")
    assert r
    assert r.new_step == "2.1 Implement element"
    assert h.step == "2.1 Implement element"
    assert h.status == "running"

    # Fix the Button atom: border-radius should inherit from context, not be hardcoded
    r = h.submit({
        "element": "Button",
        "fix": "Replaced hardcoded rounded-full with var(--button-radius, 0.375rem) so parent components can override via CSS custom property",
        "root_cause": "CardHeader sets --button-radius: 0.375rem but Button was ignoring it with !important",
    })
    assert r
    r = h.submit({
        "tests": ["Button respects --button-radius custom property", "default radius is 0.375rem when no override set"],
    })
    assert r
    r = h.submit_goto("2.0.1 Element loop")
    assert r

    # Back to page composition and integration
    assert h.step == "3.1 Compose final pages"
    assert h.status == "running"

    r = h.submit({
        "recomposition": "CardHeader now correctly renders Button with rounded-md via CSS custom property override",
    })
    assert r
    assert r.new_step == "3.2 Integration testing"
    assert h.step == "3.2 Integration testing"

    # This time all pages render correctly with proper atom styling
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 6: Stop resume
# ===============================================================

def test_stop_resume(harness_factory):
    """Friday afternoon: stop mid-molecule testing, resume Monday to continue Select atom tests."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms", "molecules"], "current_level_elements": ["select", "checkbox"]},
    )
    r = h.start()
    assert r

    # Define levels and enter inner loop
    r = h.submit({
        "levels": {"atoms": ["Select", "Checkbox"], "molecules": ["FormField", "FilterGroup"]},
    })
    assert r
    assert h.step == "2.1 Implement element"

    r = h.submit({
        "element": "Select",
        "file": "src/atoms/Select/Select.tsx",
        "implementation": "Headless UI Listbox wrapper with Tailwind, keyboard nav, multi-select option, custom option renderer slot",
    })
    assert r
    assert r.new_step == "2.2 Test element"
    assert h.step == "2.2 Test element"

    # Friday 5pm: stop to avoid pushing untested code before weekend
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Test element"

    # Monday 9am: resume where we left off
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Test element"

    # Continue writing Select tests
    r = h.submit({
        "tests": ["opens dropdown on click", "selects option with keyboard", "supports multi-select mode", "renders custom option template"],
    })
    assert r
    assert r.new_step == "2.3 Element check"
    assert h.step == "2.3 Element check"


def test_s6_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.goto("3.2 Integration testing")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_s6_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_s6_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ===============================================================
# Scenario 7: Skip level
# ===============================================================

def test_skip_level(harness_factory):
    """Skip Icon atom (using Lucide library icons), build Divider atom and both molecules from scratch."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms", "molecules"], "current_level_elements": ["icon", "divider"]},
    )
    r = h.start()
    assert r

    # Go through planning to properly initialize both loops
    r = h.submit({
        "levels": {"atoms": ["Icon", "Divider"], "molecules": ["IconButton", "SectionHeader"]},
        "note": "Icon atom wraps Lucide - may be able to skip if direct usage is sufficient",
    })
    assert r
    assert h.step == "2.1 Implement element"
    assert h.status == "running"

    # Level 1 (atoms), Element 1: Icon - skip, using Lucide directly
    r = h.skip("Using lucide-react icons directly, no wrapper atom needed - import { Search, X, ChevronDown } from 'lucide-react'")
    assert r
    assert r.new_step == "2.2 Test element"
    assert h.step == "2.2 Test element"

    r = h.skip("Lucide icons are tested upstream, no custom tests needed")
    assert r
    assert r.new_step == "2.3 Element check"
    assert h.step == "2.3 Element check"

    # skip() on LLM step triggers "needs judgment" and stays.
    # Use submit_goto to properly go through inner loop header and increment counter.
    r = h.submit_goto("2.0.1 Element loop")
    assert r
    assert r.new_step == "2.1 Implement element"
    assert h.step == "2.1 Implement element"

    # Level 1 (atoms), Element 2: Divider - build from scratch
    r = h.submit({
        "element": "Divider",
        "file": "src/atoms/Divider/Divider.tsx",
        "implementation": "Horizontal/vertical variants, customizable color via token, optional label in center",
    })
    assert r
    r = h.submit({
        "tests": ["renders horizontal by default", "renders vertical when orientation='vertical'", "shows label when provided"],
    })
    assert r
    r = h.submit_goto("2.0.1 Element loop")
    assert r
    assert h.step == "2.1 Implement element"
    assert h.status == "running"

    # Level 2 (molecules), Elements 1-2: IconButton and SectionHeader - build both
    for _ in range(2):
        r = h.submit()
        assert r
        r = h.submit()
        assert r
        r = h.submit_goto("2.0.1 Element loop")
        assert r

    assert h.step == "3.1 Compose final pages"
    assert h.status == "running"


def test_s7_skip_records_reason(harness_factory):
    """Skip reason appears in history data field."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()

    h.skip("skip planning")
    history = h.get_history(5)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "skip planning"


# ===============================================================
# Scenario 8: Done reset
# ===============================================================

def test_done_reset(harness_factory):
    """Design system v2 shipped, reset workflow to begin v3 with new brand colors from rebrand."""
    h = harness_factory(
        "p2-atomic.yaml", loop_data={"levels": ["atoms"], "current_level_elements": ["tag"]}
    )
    r = h.start()
    assert r

    # v2 is done - fast-track to completion
    r = h.goto("3.2 Integration testing")
    assert r
    assert r.new_step == "3.2 Integration testing"
    assert h.step == "3.2 Integration testing"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Marketing team completed rebrand, reset to rebuild design system with new brand palette
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define design system levels"
    assert h.status == "running"


# ===============================================================
# Scenario 9: Goto templates
# ===============================================================

def test_goto_templates(harness_factory):
    """All atoms/molecules/organisms already exist: jump straight to page composition for new marketing landing page."""
    h = harness_factory(
        "p2-atomic.yaml", loop_data={"levels": ["atoms"], "current_level_elements": ["icon"]}
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define design system levels"

    # Design system is complete, this ticket is just composing a new page from existing pieces
    r = h.goto("3.1 Compose final pages")
    assert r
    assert r.new_step == "3.1 Compose final pages"
    assert h.step == "3.1 Compose final pages"
    assert h.status == "running"

    # Compose the pricing page using existing organisms
    r = h.submit({
        "page": "PricingPage",
        "composition": "HeroSection organism + PricingTable organism + FAQ Accordion organism + CTAFooter organism",
        "layout": "Single column, max-width 1200px centered, responsive stack on mobile",
    })
    assert r
    assert r.new_step == "3.2 Integration testing"
    assert h.step == "3.2 Integration testing"
    assert h.status == "running"


# ===============================================================
# Scenario 10: Modify YAML
# ===============================================================

def test_modify_yaml_add_level(harness_factory):
    """Mid-sprint: team adds Storybook documentation generation step after Link atom is built."""
    h = harness_factory(
        "p2-atomic.yaml", loop_data={"levels": ["atoms"], "current_level_elements": ["link"]}
    )
    r = h.start()
    assert r

    # Go through planning to properly initialize loops
    r = h.submit({
        "levels": {"atoms": ["Link"]},
        "design_system": "Acme DS - adding Link atom with proper a11y for external/internal routes",
    })
    assert r
    assert h.step == "2.1 Implement element"

    # Complete the Link atom
    r = h.submit({
        "element": "Link",
        "implementation": "Polymorphic component: renders <a> for external URLs, <RouterLink> for internal paths, underline on hover, external link icon",
    })
    assert r
    r = h.submit({
        "tests": ["renders as <a> for https:// URLs", "renders as RouterLink for /paths", "adds target=_blank for external", "shows external icon"],
    })
    assert r
    r = h.submit_goto("2.0.1 Element loop")
    assert r
    assert h.step == "3.1 Compose final pages"
    assert h.status == "running"

    # Design lead mandates auto-generated Storybook docs before page composition
    modified_yaml = """name: Atomic Design Modified
description: Nested loops with documentation step

steps:
  - 1.1 Define design system levels

  - 2.0 Level loop:
      iterate: "levels"
      children:
        - 2.0.1 Element loop:
            iterate: "current_level_elements"
            children:
              - 2.1 Implement element
              - 2.2 Test element
              - 2.3 Element check:
                  next:
                    - if: "element is correct"
                      go: 2.0.1 Element loop
                    - go: 2.1 Implement element

  - 3.0 Generate design system documentation

  - 3.1 Compose final pages

  - 3.2 Integration testing:
      next:
        - if: "all pages render correctly"
          go: Done
        - go: 2.0 Level loop

  - Done:
      type: terminate
      reason: All design system levels complete
"""

    h.reload_yaml(modified_yaml)

    # Use goto to jump directly to the new documentation step
    r = h.goto("3.0 Generate design system documentation")
    assert r
    assert r.new_step == "3.0 Generate design system documentation"
    assert h.step == "3.0 Generate design system documentation"
    assert h.status == "running"

    # Auto-generate Storybook docs for all atoms
    r = h.submit({
        "tool": "storybook-autodocs",
        "output": "Generated MDX docs for 12 atoms with prop tables, usage examples, and do/dont guidelines",
        "published_to": "https://storybook.acme.dev",
    })
    assert r
    assert r.new_step == "3.1 Compose final pages"
    assert h.step == "3.1 Compose final pages"
    assert h.status == "running"


# ===============================================================
# Multi-dimension: Loop counter and cleanup
# ===============================================================

def test_inner_loop_counter_increments(harness_factory):
    """Inner loop index increments after each iteration."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["a", "b", "c"]},
    )
    _walk_to_inner_loop(h)

    inner_info = h.state.loop_state["2.0.1 Element loop"]
    assert inner_info["i"] == 0
    assert inner_info["n"] == 3

    _do_one_element(h)
    h.submit_goto("2.0.1 Element loop")

    inner_info = h.state.loop_state["2.0.1 Element loop"]
    assert inner_info["i"] == 1

    _do_one_element(h)
    h.submit_goto("2.0.1 Element loop")

    inner_info = h.state.loop_state["2.0.1 Element loop"]
    assert inner_info["i"] == 2


def test_outer_loop_cleanup_on_exit(harness_factory):
    """Both loop states are cleaned up after all iterations complete."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["only"]},
    )
    _walk_to_inner_loop(h)

    _do_one_element(h)
    h.submit_goto("2.0.1 Element loop")

    assert h.step == "3.1 Compose final pages"
    assert "2.0.1 Element loop" not in h.state.loop_state
    assert "2.0 Level loop" not in h.state.loop_state


def test_nested_loop_data_per_iteration(harness_factory):
    """Each iteration overwrites step data keys but data persists."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["a", "b"]},
    )
    _walk_to_inner_loop(h)

    h.submit({"element": "elem_a"})
    h.submit({})
    h.submit_goto("2.0.1 Element loop")

    h.submit({"element": "elem_b"})
    data = h.state.data
    assert data["2.1 Implement element"]["element"] == "elem_b"


# ===============================================================
# Multi-dimension: Node archives per iteration
# ===============================================================

def test_node_archives_per_iteration(harness_factory):
    """Archive node accumulates one row per loop iteration."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["a", "b", "c"]},
    )
    _walk_to_inner_loop(h)

    h.register_node(
        "2.1 Implement element",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"elem_name": "string"}},
            archive={"table": "atomic_elems"},
        ),
    )

    for i in range(3):
        h.submit({"elem_name": f"elem_{i}"})
        h.submit({})
        h.submit_goto("2.0.1 Element loop")

    rows = h.get_archived_rows("atomic_elems")
    assert len(rows) == 3


# ===============================================================
# Multi-dimension: Cross-executor preserves nested loops
# ===============================================================

def test_cross_executor_preserves_nested_loops(harness_factory):
    """Close executor mid-nested-loop, reopen, both loop_states intact."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms", "molecules"], "current_level_elements": ["a", "b", "c"]},
    )
    _walk_to_inner_loop(h)

    # Complete first element
    _do_one_element(h)
    h.submit_goto("2.0.1 Element loop")

    # Mid second element
    h.submit({"element": "mid_inner"})
    assert h.step == "2.2 Test element"

    h.new_executor()

    assert h.step == "2.2 Test element"
    inner_info = h.state.loop_state["2.0.1 Element loop"]
    assert inner_info["i"] == 1
    assert inner_info["n"] == 3
    outer_info = h.state.loop_state["2.0 Level loop"]
    assert outer_info["i"] == 0
    assert outer_info["n"] == 2


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.submit({})
    assert h.step == "2.1 Implement element"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()
    assert h.step == "2.1 Implement element"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.submit({"levels": "defined"})

    h.save_checkpoint("at_inner_loop")

    h.submit({})
    h.submit({})
    h.submit_goto("2.0.1 Element loop")
    assert h.step == "3.1 Compose final pages"

    restored = h.load_checkpoint("at_inner_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Implement element"
    assert "1.1 Define design system levels" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    assert h.step == "1.1 Define design system levels"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define design system levels"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.goto("3.2 Integration testing")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define design system levels"


def test_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.goto("3.2 Integration testing")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_history_records_transition_steps(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["x"]},
    )
    h.start()
    h.submit({})
    h.submit({})

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["btn"]},
    )
    h.start()
    h.submit({"levels": "defined"})

    h.register_node(
        "2.1 Implement element",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step.\n\n## Steps\n1. Analyze\n2. Implement\n3. Submit",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory(
        "p2-atomic.yaml",
        loop_data={"levels": ["atoms"], "current_level_elements": ["btn"]},
    )
    h.start()

    h.register_node(
        "1.1 Define design system levels",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="block",
                patterns=[],
            ),
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["edit_policy"] is not None
    assert status["node"]["edit_policy"]["default"] == "block"
