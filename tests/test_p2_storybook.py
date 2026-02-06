"""Test scenarios for Storybook-First workflow (p2-storybook.yaml).

Tests the Storybook-First Development workflow including:
- Setup phase (config, story list)
- Story loop with visual test 2-way branching
- Chromatic review wait with 2-way branching
- State transitions, gotos, stops/resumes, and hot-reload

Workflow structure:
  1.1 Setup Storybook config
  1.2 Define story list
  2.0 Story loop (iterate: stories)
    2.1 Write story
    2.2 Implement component for story
    2.3 Visual test (LLM 2-way: pass->2.0, fail->2.2)
  3.1 Run chromatic visual review
  3.2 Chromatic review (wait, LLM: approved->3.3, else->2.0)
  3.3 Integration
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

def _walk_to_loop(h):
    """Start -> submit 1.1 -> submit 1.2 -> arrive at 2.1 (running) in loop."""
    h.start()
    h.submit({"config": "storybook set up"})
    h.submit({"stories": "defined"})
    assert h.step == "2.1 Write story"
    assert h.status == "running"


def _do_one_story(h):
    """Complete one write-implement-visual cycle ending at visual test."""
    h.submit({"story": "written"})
    h.submit({"component": "implemented"})
    assert h.step == "2.3 Visual test"


# ===============================================================
# Scenario 1: Write 5 stories
# ===============================================================

def test_write_5_stories(harness_factory):
    """Build design system Storybook: Button, Modal, Toast, Dropdown, DataTable stories with all variants."""
    h = harness_factory(
        "p2-storybook.yaml", loop_data={"stories": ["button", "modal", "toast", "dropdown", "data_table"]}
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Setup Storybook config"
    assert h.status == "running"

    # Setup Storybook 8 with Vite builder, Tailwind addon, dark mode toggle
    r = h.submit({
        "config": {
            "framework": "@storybook/react-vite",
            "addons": ["@storybook/addon-essentials", "@storybook/addon-a11y", "storybook-dark-mode", "@storybook/addon-interactions"],
            "theme": "Custom Acme theme with brand colors",
            "global_decorators": ["ThemeProvider", "I18nProvider"],
        },
        "file": ".storybook/main.ts",
    })
    assert r
    assert r.new_step == "1.2 Define story list"
    assert h.step == "1.2 Define story list"
    assert h.status == "running"

    # Define 5 component stories with their variant matrices
    r = h.submit({
        "stories": [
            {"name": "Button", "variants": ["primary", "secondary", "ghost", "destructive"], "states": ["default", "hover", "focus", "disabled", "loading"]},
            {"name": "Modal", "variants": ["confirmation", "form", "alert"], "states": ["open", "closing-animation"]},
            {"name": "Toast", "variants": ["success", "error", "warning", "info"], "states": ["entering", "visible", "exiting"]},
            {"name": "Dropdown", "variants": ["single-select", "multi-select", "searchable"], "states": ["closed", "open", "filtered"]},
            {"name": "DataTable", "variants": ["simple", "sortable", "selectable", "paginated"], "states": ["loading", "empty", "populated", "error"]},
        ],
    })
    assert r
    assert r.new_step == "2.1 Write story"
    assert h.step == "2.1 Write story"
    assert h.status == "running"

    # Story 1: Button with all 20 variant x state combinations
    r = h.submit({
        "story": "Button",
        "file": "src/stories/Button.stories.tsx",
        "stories_written": ["Primary", "Secondary", "Ghost", "Destructive", "AllSizes", "WithIcon", "Loading", "Disabled"],
        "args_table": "Auto-generated from TypeScript props via autodocs",
    })
    assert r
    assert r.new_step == "2.2 Implement component for story"
    assert h.step == "2.2 Implement component for story"

    r = h.submit({
        "component": "Button",
        "file": "src/components/Button/Button.tsx",
        "implementation": "CVA variants with Tailwind, forwardRef, polymorphic 'as' prop, Slot pattern for composition, loading spinner overlay",
    })
    assert r
    assert r.new_step == "2.3 Visual test"
    assert h.step == "2.3 Visual test"

    # Visual test passes for Button
    r = h.submit_goto("2.0 Story loop")
    assert r
    assert r.new_step == "2.1 Write story"
    assert h.step == "2.1 Write story"

    # Stories 2-5: Modal, Toast, Dropdown, DataTable
    for _ in range(4):
        r = h.submit()
        assert r
        r = h.submit()
        assert r
        r = h.submit_goto("2.0 Story loop")
        assert r

    # Exit loop, run Chromatic visual review
    assert h.step == "3.1 Run chromatic visual review"
    assert h.status == "running"

    r = h.submit({
        "chromatic_build": "Build #847",
        "snapshots": 156,
        "changes_detected": 0,
        "browsers_tested": ["Chrome", "Firefox", "Safari", "Edge"],
    })
    assert r
    assert r.new_step == "3.2 Chromatic review"
    assert h.step == "3.2 Chromatic review"
    assert h.status == "waiting"

    # Design team approves all visual snapshots
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("3.3 Integration")
    assert r
    assert r.new_step == "3.3 Integration"
    assert h.step == "3.3 Integration"
    assert h.status == "running"

    r = h.submit({
        "integration": "All 5 components render correctly in application context",
        "bundle_size": "Tree-shaking verified: unused stories not included in production build",
        "storybook_url": "https://storybook.acme.dev/v2.1.0",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["card"]})
    h.start()

    h.submit({"config": "storybook ready"})
    data = h.state.data
    assert "1.1 Setup Storybook config" in data
    assert data["1.1 Setup Storybook config"]["config"] == "storybook ready"

    h.submit({"stories": "card only"})
    data = h.state.data
    assert "1.2 Define story list" in data
    assert data["1.2 Define story list"]["stories"] == "card only"

    h.submit({"story": "card story"})
    data = h.state.data
    assert "2.1 Write story" in data
    assert data["2.1 Write story"]["story"] == "card story"


def test_s1_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["s1"]})
    h.start()
    h.submit({})
    h.submit({})
    # Loop
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Story loop")
    # After 1 story, loop exits
    assert h.step == "3.1 Run chromatic visual review"
    h.submit({})
    assert h.step == "3.2 Chromatic review"
    h.approve()
    h.submit_goto("3.3 Integration")
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "approve" in actions
    assert "terminate" in actions[-1]


def test_s1_cross_executor_at_setup(harness_factory):
    """Close executor at setup phase, reopen, continue."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({"config": "ready"})
    assert h.step == "1.2 Define story list"

    h.new_executor()

    assert h.step == "1.2 Define story list"
    assert h.status == "running"

    r = h.submit({"stories": "defined"})
    assert r
    assert h.step == "2.1 Write story"


def test_s1_cross_executor_at_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state preserved."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["a", "b"]})
    _walk_to_loop(h)

    h.submit({"story": "a_story"})
    assert h.step == "2.2 Implement component for story"

    h.new_executor()

    assert h.step == "2.2 Implement component for story"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Story loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_s1_node_validates_story(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["card"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Write story",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("story") else "must include story content",
        ),
    )

    # Bad data
    r = h.submit({"notes": "forgot"})
    assert not r
    assert "rejected" in r.message.lower()

    # Good data
    r = h.submit({"story": "card story"})
    assert r
    assert r.new_step == "2.2 Implement component for story"


def test_s1_node_archives_stories(harness_factory):
    """Archive node writes submitted data to SQLite table."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["a", "b"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Write story",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"story_name": "string", "type": "string"}},
            archive={"table": "stories_written"},
        ),
    )

    h.submit({"story_name": "login", "type": "form"})
    h.submit({})
    h.submit_goto("2.0 Story loop")
    h.submit({"story_name": "dashboard", "type": "layout"})

    rows = h.get_archived_rows("stories_written")
    assert len(rows) == 2
    assert rows[0]["story_name"] == "login"
    assert rows[1]["story_name"] == "dashboard"


# ===============================================================
# Scenario 2: Visual test fail fix
# ===============================================================

def test_visual_test_fail_fix(harness_factory):
    """Card story visual test fails 4 rounds: shadow, border-radius, image aspect-ratio, dark mode colors."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["product_card"]})
    r = h.start()
    assert r

    # Go through setup to properly initialize loop
    r = h.submit({
        "config": {"framework": "@storybook/react-vite", "addons": ["chromatic", "addon-a11y"]},
    })
    assert r
    r = h.submit({
        "stories": [{"name": "ProductCard", "variants": ["default", "sale", "out-of-stock", "featured"]}],
    })
    assert r
    assert h.step == "2.1 Write story"
    assert h.status == "running"

    # Write ProductCard story and initial implementation
    r = h.submit({
        "story": "ProductCard",
        "file": "src/stories/ProductCard.stories.tsx",
        "stories_written": ["Default", "OnSale", "OutOfStock", "Featured", "WithLongTitle", "NoImage"],
    })
    assert r
    r = h.submit({
        "component": "ProductCard",
        "implementation": "Card with image, title, price, add-to-cart CTA, sale badge overlay",
    })
    assert r
    assert h.step == "2.3 Visual test"

    # Round 1: box-shadow too strong, creates visual noise in card grid
    r = h.submit_goto("2.2 Implement component for story")
    assert r
    assert r.new_step == "2.2 Implement component for story"
    assert h.step == "2.2 Implement component for story"

    r = h.submit({
        "component": "ProductCard",
        "fix": "Reduced shadow from shadow-lg to shadow-sm, added shadow-md on hover for subtle lift effect",
    })
    assert r
    assert r.new_step == "2.3 Visual test"
    assert h.step == "2.3 Visual test"

    # Round 2: border-radius inconsistent with design system (16px vs spec 12px)
    # Round 3: product image aspect ratio distorts on non-square images
    for fix in [
        "Changed border-radius from rounded-2xl (16px) to rounded-xl (12px) to match design system token",
        "Added aspect-ratio: 4/3 with object-cover to product image container, prevents distortion on any image ratio",
    ]:
        r = h.submit_goto("2.2 Implement component for story")
        assert r
        r = h.submit({"component": "ProductCard", "fix": fix})
        assert r
        assert h.step == "2.3 Visual test"

    # Round 4: dark mode colors - price text invisible on dark background
    r = h.submit_goto("2.2 Implement component for story")
    assert r
    r = h.submit({
        "component": "ProductCard",
        "fix": "Price text: changed from text-gray-900 to text-foreground (maps to white in dark mode), sale badge uses destructive token for both themes",
        "visual_qa": "Chromatic snapshot matches Figma spec for all 6 story variants in both light and dark mode",
    })
    assert r
    assert h.step == "2.3 Visual test"

    # This time it passes
    r = h.submit_goto("2.0 Story loop")
    assert r
    assert r.new_step == "3.1 Run chromatic visual review"
    assert h.step == "3.1 Run chromatic visual review"
    assert h.status == "running"


def test_s2_data_has_all_attempts(harness_factory):
    """All fix attempts store data (last wins per step key)."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({})
    h.submit({})
    h.goto("2.2 Implement component for story")

    for i in range(4):
        h.submit({"component": f"attempt_{i}"})
        if h.step != "2.2 Implement component for story":
            h.goto("2.2 Implement component for story")

    data = h.state.data
    assert "2.2 Implement component for story" in data


def test_s2_cross_executor_mid_retry(harness_factory):
    """Close executor after retries, reopen, continue from same step."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    assert h.step == "2.3 Visual test"

    for _ in range(2):
        h.submit_goto("2.2 Implement component for story")
        h.submit({})
    assert h.step == "2.3 Visual test"

    h.new_executor()
    assert h.step == "2.3 Visual test"
    assert h.status == "running"


# ===============================================================
# Scenario 3: Chromatic rejected back
# ===============================================================

def test_chromatic_rejected_back(harness_factory):
    """Chromatic review: design team rejects Tabs component — active indicator 2px off from Figma spec."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["tabs"]})
    r = h.start()
    assert r

    # Go through setup and loop to reach chromatic review naturally
    r = h.submit({
        "config": {"framework": "@storybook/react-vite", "addons": ["chromatic"]},
    })
    assert r
    r = h.submit({
        "stories": [{"name": "Tabs", "variants": ["default", "pills", "underline"]}],
    })
    assert r
    assert h.step == "2.1 Write story"

    r = h.submit({
        "story": "Tabs",
        "file": "src/stories/Tabs.stories.tsx",
    })
    assert r
    r = h.submit({
        "component": "Tabs",
        "implementation": "Radix UI Tabs primitive with animated underline indicator using Framer Motion layoutId",
    })
    assert r
    r = h.submit_goto("2.0 Story loop")
    assert r
    assert h.step == "3.1 Run chromatic visual review"
    assert h.status == "running"

    r = h.submit({
        "chromatic_build": "Build #312",
        "changes_detected": 3,
        "diff_pixels": "Active tab underline is 2px lower than Figma spec across all 3 variants",
    })
    assert r
    assert r.new_step == "3.2 Chromatic review"
    assert h.step == "3.2 Chromatic review"
    assert h.status == "waiting"

    # Design team rejects: underline position off
    r = h.reject("Tab underline indicator is 2px below the Figma spec baseline. Please adjust bottom offset.")
    assert r
    assert h.step == "3.2 Chromatic review"
    assert h.status == "waiting"

    # Go back to fix the component
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Story loop")
    assert r
    assert r.new_step == "2.1 Write story"
    assert h.step == "2.1 Write story"
    assert h.status == "running"

    # Fix the Tab underline offset
    r = h.submit()
    assert r
    r = h.submit({
        "component": "Tabs",
        "fix": "Changed underline bottom offset from -2px to 0px, now flush with tab content baseline per Figma spec",
    })
    assert r
    r = h.submit_goto("2.0 Story loop")
    assert r
    assert h.step == "3.1 Run chromatic visual review"

    r = h.submit({
        "chromatic_build": "Build #313",
        "changes_detected": 3,
        "status": "All 3 changes match updated Figma spec, no unexpected regressions",
    })
    assert r
    assert r.new_step == "3.2 Chromatic review"
    assert h.step == "3.2 Chromatic review"
    assert h.status == "waiting"

    # This time design team approves
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("3.3 Integration")
    assert r
    assert r.new_step == "3.3 Integration"
    assert h.step == "3.3 Integration"
    assert h.status == "running"


def test_s3_chromatic_reject_preserves_data(harness_factory):
    """Reject does not modify state.data."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Story loop")
    h.submit({})
    assert h.step == "3.2 Chromatic review"
    assert h.status == "waiting"

    data_before = dict(h.state.data)
    h.reject("needs fixes")
    data_after = h.state.data
    assert data_before == data_after


def test_s3_chromatic_reject_adds_history(harness_factory):
    """Reject action appears in history."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Story loop")
    h.submit({})
    assert h.step == "3.2 Chromatic review"
    h.reject("bad review")

    history = h.get_history(30)
    reject_entries = [e for e in history if e["action"] == "reject"]
    assert len(reject_entries) >= 1
    assert reject_entries[0]["data"] == "bad review"


# ===============================================================
# Scenario 4: Empty story list
# ===============================================================

def test_empty_story_list(harness_factory):
    """Storybook config-only ticket: update global decorators and theme, no new stories to write."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": []})
    r = h.start()
    assert r

    # Setup: update Storybook from v7 to v8, migrate config
    r = h.submit({
        "config": "Migrated .storybook/main.js to .storybook/main.ts, upgraded to Storybook 8 with Vite builder",
        "migration": "Ran npx storybook@latest upgrade, fixed 3 deprecated addon imports",
    })
    assert r
    r = h.submit({
        "stories": [],
        "reason": "Config-only update: no new component stories, just framework migration and theme update",
    })
    assert r

    # Loop should exit immediately - no stories to write
    assert h.step == "3.1 Run chromatic visual review"
    assert h.status == "running"


# ===============================================================
# Scenario 5: Skip story
# ===============================================================

def test_skip_story(harness_factory):
    """Three stories: build Avatar and Tooltip from scratch, skip Spinner (already has story from upstream package)."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["avatar", "spinner", "tooltip"]})
    r = h.start()
    assert r

    # Go through setup to properly initialize loop
    r = h.submit({
        "config": {"framework": "@storybook/react-vite"},
    })
    assert r
    r = h.submit({
        "stories": [
            {"name": "Avatar", "priority": "high"},
            {"name": "Spinner", "priority": "low", "note": "Already has story in @acme/primitives"},
            {"name": "Tooltip", "priority": "high"},
        ],
    })
    assert r
    assert h.step == "2.1 Write story"
    assert h.status == "running"

    # Story 1: Avatar - write story and implement
    r = h.submit({
        "story": "Avatar",
        "file": "src/stories/Avatar.stories.tsx",
        "stories_written": ["WithImage", "WithInitials", "WithStatus", "Sizes", "Group"],
    })
    assert r
    r = h.submit({
        "component": "Avatar",
        "implementation": "Radix Avatar primitive with image fallback to initials, online/offline/busy status dot",
    })
    assert r
    r = h.submit_goto("2.0 Story loop")
    assert r
    assert r.new_step == "2.1 Write story"
    assert h.step == "2.1 Write story"

    # Story 2: Spinner - skip, already exists in upstream package
    r = h.skip("Spinner story already exists in @acme/primitives Storybook, re-exporting as-is")
    assert r
    assert r.new_step == "2.2 Implement component for story"
    assert h.step == "2.2 Implement component for story"

    r = h.skip("Spinner component is a direct re-export from @acme/primitives, no custom implementation needed")
    assert r
    assert r.new_step == "2.3 Visual test"
    assert h.step == "2.3 Visual test"

    # skip() on LLM step doesn't move - use submit_goto to go through loop header
    r = h.submit_goto("2.0 Story loop")
    assert r
    assert r.new_step == "2.1 Write story"
    assert h.step == "2.1 Write story"

    # Story 3: Tooltip - write and implement
    r = h.submit({
        "story": "Tooltip",
        "file": "src/stories/Tooltip.stories.tsx",
        "stories_written": ["Default", "WithArrow", "Positions", "Delayed", "Interactive"],
    })
    assert r
    r = h.submit({
        "component": "Tooltip",
        "implementation": "Radix Tooltip with custom portal, configurable delay, arrow, and interactive content support",
    })
    assert r
    r = h.submit_goto("2.0 Story loop")
    assert r

    # Exit loop
    assert h.step == "3.1 Run chromatic visual review"
    assert h.status == "running"


def test_s5_skip_records_reason(harness_factory):
    """Skip reason appears in history data field."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()

    h.skip("skip config")
    history = h.get_history(5)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "skip config"


# ===============================================================
# Scenario 6: Stop resume
# ===============================================================

def test_stop_resume(harness_factory):
    """Writing Modal and Dialog stories: stop for team demo, resume after lunch to finish Dialog implementation."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["modal", "dialog"]})
    r = h.start()
    assert r

    # Setup and define stories
    r = h.submit({
        "config": {"framework": "@storybook/react-vite", "addons": ["addon-interactions"]},
    })
    assert r
    r = h.submit({
        "stories": [{"name": "Modal", "variants": ["default", "full-screen", "drawer"]}, {"name": "Dialog", "variants": ["alert", "confirm", "prompt"]}],
    })
    assert r
    assert h.step == "2.1 Write story"

    r = h.submit({
        "story": "Modal",
        "file": "src/stories/Modal.stories.tsx",
        "stories_written": ["Default", "FullScreen", "Drawer", "WithForm", "NestedModal"],
    })
    assert r
    assert r.new_step == "2.2 Implement component for story"
    assert h.step == "2.2 Implement component for story"

    # Team demo in 5 minutes - stop to present current Storybook progress
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Implement component for story"

    # After demo and lunch, resume implementing Modal component
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Implement component for story"

    # Continue implementing Modal
    r = h.submit({
        "component": "Modal",
        "implementation": "Radix Dialog with portal, focus trap, scroll lock, animated backdrop with Framer Motion",
    })
    assert r
    assert r.new_step == "2.3 Visual test"
    assert h.step == "2.3 Visual test"


def test_s6_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.goto("3.3 Integration")
    h.submit({})
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_s6_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_s6_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


def test_s6_stop_resume_at_chromatic_review(harness_factory):
    """Stop at chromatic review wait step, resume restores waiting."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Story loop")
    h.submit({})
    assert h.step == "3.2 Chromatic review"
    assert h.status == "waiting"

    h.stop()
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"
    assert h.step == "3.2 Chromatic review"


# ===============================================================
# Scenario 7: Done reset
# ===============================================================

def test_done_reset(harness_factory):
    """Storybook v2.0 published, reset to start v3.0 with new design tokens from rebrand."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["icon"]})
    r = h.start()
    assert r

    # v2.0 is done, fast-track to completion
    r = h.goto("3.3 Integration")
    assert r
    assert r.new_step == "3.3 Integration"
    assert h.step == "3.3 Integration"
    assert h.status == "running"

    r = h.submit({
        "integration": "Storybook v2.0 deployed to https://storybook.acme.dev",
        "components": 24,
        "stories": 156,
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Company rebrand complete, reset to rebuild all stories with new design tokens
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Setup Storybook config"
    assert h.status == "running"


# ===============================================================
# Scenario 8: Back
# ===============================================================

def test_back(harness_factory):
    """Accordion story: go back to fix Storybook config (missing viewport addon), then back to rewrite story args."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["accordion"]})
    r = h.start()
    assert r

    r = h.submit({
        "config": {"framework": "@storybook/react-vite", "addons": ["addon-essentials"]},
    })
    assert r
    assert r.new_step == "1.2 Define story list"
    assert h.step == "1.2 Define story list"

    # Go back: realized we need @storybook/addon-viewport for responsive stories
    r = h.back()
    assert r
    assert r.new_step == "1.1 Setup Storybook config"
    assert h.step == "1.1 Setup Storybook config"
    assert h.status == "running"

    # Continue forward with fixed config
    r = h.submit()
    assert r
    r = h.submit()
    assert r
    assert h.step == "2.1 Write story"

    r = h.submit({
        "story": "Accordion",
        "file": "src/stories/Accordion.stories.tsx",
        "stories_written": ["Default", "Multiple", "Controlled", "WithIcons"],
    })
    assert r
    assert r.new_step == "2.2 Implement component for story"
    assert h.step == "2.2 Implement component for story"

    # Go back: story needs a "Disabled" variant that was missed
    r = h.back()
    assert r
    assert r.new_step == "2.1 Write story"
    assert h.step == "2.1 Write story"
    assert h.status == "running"


# ===============================================================
# Scenario 9: Goto integration
# ===============================================================

def test_goto_integration(harness_factory):
    """Badge component: stories already written and reviewed, jump to integration to verify in-app rendering."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["badge"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Setup Storybook config"

    # Badge stories were completed in a previous session, jump to integration testing
    r = h.goto("3.3 Integration")
    assert r
    assert r.new_step == "3.3 Integration"
    assert h.step == "3.3 Integration"
    assert h.status == "running"

    # Verify Badge renders correctly in production app context
    r = h.submit({
        "integration": "Badge component integrates correctly in NotificationList, UserProfile, and OrderStatus views",
        "verified_contexts": ["inline with text", "on avatar", "in table cell", "with count > 99 truncation"],
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 10: Modify YAML
# ===============================================================

def test_modify_yaml_add_story(harness_factory):
    """Mid-sprint SOP change: add mandatory axe-core accessibility audit before Chromatic visual review."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["popover"]})
    r = h.start()
    assert r

    # Go through setup to properly initialize loop
    r = h.submit({
        "config": {"framework": "@storybook/react-vite", "addons": ["addon-a11y"]},
    })
    assert r
    r = h.submit({
        "stories": [{"name": "Popover", "variants": ["default", "with-arrow", "nested"]}],
    })
    assert r
    assert h.step == "2.1 Write story"

    # Complete Popover story loop
    r = h.submit({
        "story": "Popover",
        "file": "src/stories/Popover.stories.tsx",
    })
    assert r
    r = h.submit({
        "component": "Popover",
        "implementation": "Floating UI-based popover with auto-placement, focus trap, and dismiss on escape",
    })
    assert r
    r = h.submit_goto("2.0 Story loop")
    assert r
    assert h.step == "3.1 Run chromatic visual review"
    assert h.status == "running"

    # Accessibility team mandates axe-core audit step after recent WCAG complaint
    modified_yaml = """名称: Storybook-First Development Modified
描述: Story loop with accessibility check

步骤:
  - 1.1 Setup Storybook config

  - 1.2 Define story list

  - 2.0 Story loop:
      遍历: "stories"
      子步骤:
        - 2.1 Write story
        - 2.2 Implement component for story
        - 2.3 Visual test:
            下一步:
              - 如果: "visual test passes"
                去: 2.0 Story loop
              - 去: 2.2 Implement component for story

  - 2.9 Run accessibility audit

  - 3.1 Run chromatic visual review

  - 3.2 Chromatic review:
      类型: wait
      下一步:
        - 如果: "chromatic review approved"
          去: 3.3 Integration
        - 去: 2.0 Story loop

  - 3.3 Integration

  - Done:
      类型: terminate
      原因: All stories pass visual review
"""

    h.reload_yaml(modified_yaml)

    # Jump to the new accessibility audit step
    r = h.goto("2.9 Run accessibility audit")
    assert r
    assert r.new_step == "2.9 Run accessibility audit"
    assert h.step == "2.9 Run accessibility audit"
    assert h.status == "running"

    # Run axe-core on all story variants
    r = h.submit({
        "tool": "axe-core via @storybook/addon-a11y",
        "stories_audited": 8,
        "violations": 0,
        "passes": ["color-contrast", "aria-roles", "focus-management", "keyboard-navigation"],
        "result": "All Popover stories pass WCAG 2.1 AA",
    })
    assert r
    assert r.new_step == "3.1 Run chromatic visual review"
    assert h.step == "3.1 Run chromatic visual review"
    assert h.status == "running"


# ===============================================================
# Multi-dimension: Loop counter and cleanup
# ===============================================================

def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["a", "b", "c"]})
    _walk_to_loop(h)

    loop_info = h.state.loop_state["2.0 Story loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_story(h)
    h.submit_goto("2.0 Story loop")

    loop_info = h.state.loop_state["2.0 Story loop"]
    assert loop_info["i"] == 1

    _do_one_story(h)
    h.submit_goto("2.0 Story loop")

    loop_info = h.state.loop_state["2.0 Story loop"]
    assert loop_info["i"] == 2


def test_loop_cleanup_on_exit(harness_factory):
    """Loop state is cleaned up after all iterations complete."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["only"]})
    _walk_to_loop(h)

    _do_one_story(h)
    h.submit_goto("2.0 Story loop")

    assert h.step == "3.1 Run chromatic visual review"
    assert "2.0 Story loop" not in h.state.loop_state


def test_loop_data_per_iteration(harness_factory):
    """Each iteration overwrites step data keys but data persists."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["a", "b"]})
    _walk_to_loop(h)

    h.submit({"story": "story_a"})
    h.submit({})
    h.submit_goto("2.0 Story loop")

    h.submit({"story": "story_b"})
    data = h.state.data
    assert data["2.1 Write story"]["story"] == "story_b"


# ===============================================================
# Multi-dimension: Node archives per iteration
# ===============================================================

def test_node_archives_per_iteration(harness_factory):
    """Archive node accumulates one row per loop iteration."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["a", "b", "c"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Write story",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"story_name": "string"}},
            archive={"table": "sb_stories"},
        ),
    )

    for i in range(3):
        h.submit({"story_name": f"story_{i}"})
        h.submit({})
        h.submit_goto("2.0 Story loop")

    rows = h.get_archived_rows("sb_stories")
    assert len(rows) == 3


# ===============================================================
# Multi-dimension: Cross-executor preserves loop
# ===============================================================

def test_cross_executor_preserves_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state intact."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["a", "b", "c"]})
    _walk_to_loop(h)

    _do_one_story(h)
    h.submit_goto("2.0 Story loop")

    # Mid iteration 2
    h.submit({"story": "mid_loop"})
    assert h.step == "2.2 Implement component for story"

    h.new_executor()

    assert h.step == "2.2 Implement component for story"
    loop_info = h.state.loop_state["2.0 Story loop"]
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Define story list"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()
    assert h.step == "1.2 Define story list"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({"config": "ready"})
    h.submit({"stories": "defined"})

    h.save_checkpoint("at_loop_entry")

    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Story loop")
    assert h.step == "3.1 Run chromatic visual review"

    restored = h.load_checkpoint("at_loop_entry")
    assert restored is not None
    assert restored.current_step == "2.1 Write story"
    assert "1.2 Define story list" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    assert h.step == "1.1 Setup Storybook config"

    r = h.retry()
    assert r
    assert h.step == "1.1 Setup Storybook config"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.goto("3.3 Integration")
    h.submit({})
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Setup Storybook config"


def test_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.goto("3.3 Integration")
    h.submit({})
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_approve_on_non_waiting_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_wait_step_rejects_submit(harness_factory):
    """At chromatic review wait step, submit is rejected."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Story loop")
    h.submit({})
    assert h.step == "3.2 Chromatic review"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_history_records_transition_steps(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["x"]})
    h.start()
    h.submit({})
    h.submit({})

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["card"]})
    h.start()
    h.submit({"config": "storybook set up"})
    h.submit({"stories": "defined"})

    h.register_node(
        "2.1 Write story",
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
    h = harness_factory("p2-storybook.yaml", loop_data={"stories": ["card"]})
    h.start()

    h.register_node(
        "1.1 Setup Storybook config",
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
