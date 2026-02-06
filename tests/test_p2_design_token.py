"""Test scenarios for Design-Token workflow (p2-design-token.yaml).

Tests the Design-Token-Based Development workflow including:
- Token definition wait and review wait with 2-way branching
- Component loop with token usage check
- Consistency audit with 2-way branching
- State transitions, gotos, stops/resumes, and hot-reload

Workflow structure:
  1.1 Define design tokens (wait)
  1.2 Token review (wait, LLM: approved->2.0, else->1.1)
  2.0 Component loop (iterate: components)
    2.1 Implement component with tokens
    2.2 Test component
    2.3 Component check (LLM 2-way: pass->2.0, fail->2.1)
  3.1 Consistency audit (LLM: pass->3.2, fail->2.0)
  3.2 Generate documentation
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
    """Start -> approve 1.1 -> approve 1.2 -> submit_goto 2.0 -> at 2.1 (running)."""
    h.start()
    h.approve({"tokens": "colors, spacing"})
    h.approve()
    h.submit_goto("2.0 Component loop")
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"


def _do_one_component(h):
    """Complete one implement-test-check cycle ending at component check."""
    h.submit({"component": "impl"})
    h.submit({"tests": "pass"})
    assert h.step == "2.3 Component check"


# ===============================================================
# Scenario 1: Define tokens, 5 components
# ===============================================================

def test_define_tokens_5_components(harness_factory):
    """Define Figma-synced design tokens, review with design team, build 5 components using token system."""
    h = harness_factory(
        "p2-design-token.yaml",
        loop_data={"components": ["nav_bar", "button", "card", "text_input", "dialog"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define design tokens"
    assert h.status == "waiting"

    # Designer provides token definitions exported from Figma via Token Studio
    r = h.approve({
        "tokens": {
            "color": {
                "primary": {"value": "#2563EB", "description": "Primary brand blue"},
                "primary-hover": {"value": "#1D4ED8"},
                "destructive": {"value": "#DC2626"},
                "background": {"value": "#FFFFFF", "dark": "#0F172A"},
                "foreground": {"value": "#0F172A", "dark": "#F8FAFC"},
                "muted": {"value": "#F1F5F9", "dark": "#1E293B"},
            },
            "spacing": {"xs": "4px", "sm": "8px", "md": "16px", "lg": "24px", "xl": "32px"},
            "radius": {"sm": "4px", "md": "8px", "lg": "12px", "full": "9999px"},
            "typography": {
                "heading-lg": {"size": "30px", "weight": "700", "line_height": "36px"},
                "body": {"size": "14px", "weight": "400", "line_height": "20px"},
            },
            "shadow": {"sm": "0 1px 2px rgba(0,0,0,0.05)", "md": "0 4px 6px rgba(0,0,0,0.1)"},
        },
        "format": "CSS custom properties via tokens.css, Tailwind config extends via tailwind.config.ts",
        "source": "Figma Token Studio plugin, synced via GitHub Action",
    })
    assert r
    assert r.new_step == "1.2 Token review"
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    # Design team reviews and approves token values
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component with tokens"
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"

    # Component 1: NavBar using color.primary, spacing.md, shadow.sm
    r = h.submit({
        "component": "NavBar",
        "file": "src/components/NavBar/NavBar.tsx",
        "tokens_used": ["color.primary", "color.background", "spacing.md", "shadow.sm"],
        "implementation": "Sticky nav with bg-background, shadow-sm, logo + links with text-foreground, active link uses border-b-2 border-primary",
    })
    assert r
    assert r.new_step == "2.2 Test component"
    assert h.step == "2.2 Test component"

    r = h.submit({
        "tests": ["uses --color-background for bg", "active link has primary border", "switches colors in dark mode"],
        "token_coverage": "All 4 tokens verified in test assertions",
    })
    assert r
    assert r.new_step == "2.3 Component check"
    assert h.step == "2.3 Component check"

    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component with tokens"
    assert h.step == "2.1 Implement component with tokens"

    # Components 2-5: Button, Card, TextInput, Dialog
    for _ in range(4):
        r = h.submit()
        assert r
        r = h.submit()
        assert r
        r = h.submit_goto("2.0 Component loop")
        assert r

    # Exit loop, consistency audit
    assert h.step == "3.1 Consistency audit"
    assert h.status == "running"

    # Audit: all components consistently use tokens, no hardcoded values
    r = h.submit_goto("3.2 Generate documentation")
    assert r
    assert r.new_step == "3.2 Generate documentation"
    assert h.step == "3.2 Generate documentation"

    r = h.submit({
        "docs": "Auto-generated token reference with color swatches, spacing scale visualization, and component usage examples",
        "output": "docs/design-tokens.mdx published to internal Storybook",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_s1_data_accumulates(harness_factory):
    """Each submit/approve stores data keyed by step name."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["btn"]})
    h.start()

    h.approve({"tokens": "colors only"})
    data = h.state.data
    assert "1.1 Define design tokens" in data
    assert data["1.1 Define design tokens"]["tokens"] == "colors only"

    h.approve()
    h.submit_goto("2.0 Component loop")

    h.submit({"component": "button"})
    data = h.state.data
    assert "2.1 Implement component with tokens" in data
    assert data["2.1 Implement component with tokens"]["component"] == "button"


def test_s1_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["c1"]})
    h.start()
    h.approve({})
    h.approve()
    h.submit_goto("2.0 Component loop")
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Component loop")
    assert h.step == "3.1 Consistency audit"
    h.submit_goto("3.2 Generate documentation")
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "approve" in actions
    assert "submit" in actions
    assert "terminate" in actions[-1]


def test_s1_cross_executor_at_token_review(harness_factory):
    """Close executor at token review, reopen, continue."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.approve({"tokens": "defined"})
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    h.approve()
    r = h.submit_goto("2.0 Component loop")
    assert r
    assert h.step == "2.1 Implement component with tokens"


def test_s1_cross_executor_at_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state preserved."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["a", "b"]})
    _walk_to_loop(h)

    h.submit({"component": "a_impl"})
    assert h.step == "2.2 Test component"

    h.new_executor()

    assert h.step == "2.2 Test component"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Component loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_s1_node_validates_component(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["btn"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Implement component with tokens",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("component") else "must include component name",
        ),
    )

    # Bad data
    r = h.submit({"notes": "forgot"})
    assert not r
    assert "rejected" in r.message.lower()

    # Good data
    r = h.submit({"component": "button"})
    assert r
    assert r.new_step == "2.2 Test component"


def test_s1_node_archives_components(harness_factory):
    """Archive node writes submitted data to SQLite table."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["a", "b"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Implement component with tokens",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"name": "string", "token_usage": "string"}},
            archive={"table": "token_components"},
        ),
    )

    h.submit({"name": "header", "token_usage": "colors, spacing"})
    h.submit({})
    h.submit_goto("2.0 Component loop")
    h.submit({"name": "card", "token_usage": "colors"})

    rows = h.get_archived_rows("token_components")
    assert len(rows) == 2
    assert rows[0]["name"] == "header"
    assert rows[1]["name"] == "card"


# ===============================================================
# Scenario 2: Token review rejected
# ===============================================================

def test_token_review_rejected(harness_factory):
    """Token review rejected twice: contrast ratio fails WCAG, then spacing scale inconsistent. Third attempt approved."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["btn"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define design tokens"
    assert h.status == "waiting"

    # First token definition attempt
    r = h.approve({
        "tokens": {
            "color": {"primary": "#60A5FA", "on-primary": "#FFFFFF", "background": "#FFFFFF"},
            "spacing": {"sm": "6px", "md": "12px", "lg": "20px"},
        },
    })
    assert r
    assert r.new_step == "1.2 Token review"
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    # Rejected: primary color #60A5FA on white background fails WCAG AA contrast (3.1:1, needs 4.5:1)
    r = h.reject("color.primary #60A5FA on white fails WCAG AA contrast ratio (3.1:1). Need at least 4.5:1 for body text.")
    assert r
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    # Go back to fix colors
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("1.1 Define design tokens")
    assert r
    assert r.new_step == "1.1 Define design tokens"
    assert h.step == "1.1 Define design tokens"
    assert h.status == "waiting"

    # Second attempt: fixed contrast but spacing scale is non-standard
    r = h.approve({
        "tokens": {
            "color": {"primary": "#2563EB", "on-primary": "#FFFFFF", "background": "#FFFFFF"},
            "spacing": {"sm": "6px", "md": "14px", "lg": "20px"},
        },
    })
    assert r
    assert r.new_step == "1.2 Token review"
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    # Rejected: spacing scale should follow 4px grid (4, 8, 16, 24, 32), not arbitrary values
    r = h.reject("Spacing scale must follow 4px grid system. 6px and 14px are off-grid. Use 4/8/16/24/32.")
    assert r
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    # Go back to fix spacing
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("1.1 Define design tokens")
    assert r
    assert r.new_step == "1.1 Define design tokens"
    assert h.step == "1.1 Define design tokens"
    assert h.status == "waiting"

    # Third attempt: proper contrast AND 4px grid spacing
    r = h.approve({
        "tokens": {
            "color": {"primary": "#2563EB", "on-primary": "#FFFFFF", "background": "#FFFFFF"},
            "spacing": {"xs": "4px", "sm": "8px", "md": "16px", "lg": "24px", "xl": "32px"},
        },
        "wcag_contrast": "7.1:1 (AAA compliant)",
        "grid_system": "4px base unit",
    })
    assert r
    assert r.new_step == "1.2 Token review"
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    # Approved: contrast and spacing both meet standards
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component with tokens"
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"


def test_s2_reject_preserves_data(harness_factory):
    """Reject does not modify state.data."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.approve({"tokens": "defined"})
    assert h.step == "1.2 Token review"

    data_before = dict(h.state.data)
    h.reject("nope")
    data_after = h.state.data
    assert data_before == data_after


def test_s2_reject_adds_history(harness_factory):
    """Reject action appears in history."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.approve({})
    h.reject("bad tokens")

    history = h.get_history(10)
    reject_entries = [e for e in history if e["action"] == "reject"]
    assert len(reject_entries) >= 1
    assert reject_entries[0]["data"] == "bad tokens"


# ===============================================================
# Scenario 3: Consistency fail
# ===============================================================

def test_consistency_fail(harness_factory):
    """Consistency audit finds Sidebar using hardcoded #333 instead of color.foreground token. Fix and re-audit."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["sidebar"]})
    r = h.start()
    assert r

    # Jump to consistency audit
    r = h.goto("3.1 Consistency audit")
    assert r
    assert r.new_step == "3.1 Consistency audit"
    assert h.step == "3.1 Consistency audit"
    assert h.status == "running"

    # Audit finds Sidebar has hardcoded color values
    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component with tokens"
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"

    # Fix Sidebar to use tokens
    r = h.submit({
        "component": "Sidebar",
        "fix": "Replaced hardcoded #333 with var(--color-foreground), #f5f5f5 with var(--color-muted), 16px with var(--spacing-md)",
        "tokens_now_used": ["color.foreground", "color.muted", "color.background", "spacing.md", "spacing.lg", "radius.md"],
    })
    assert r
    r = h.submit({
        "tests": ["verifies all CSS values reference token custom properties", "dark mode switches correctly"],
    })
    assert r
    r = h.submit_goto("2.0 Component loop")
    assert r

    # Back to audit
    assert h.step == "3.1 Consistency audit"
    assert h.status == "running"

    # This time all components are consistent with design tokens
    r = h.submit_goto("3.2 Generate documentation")
    assert r
    assert r.new_step == "3.2 Generate documentation"
    assert h.step == "3.2 Generate documentation"

    r = h.submit({
        "docs": "Token usage report: 100% of color/spacing/radius values reference design tokens. Zero hardcoded values found.",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 4: Skip docs
# ===============================================================

def test_skip_docs(harness_factory):
    """Internal tooling project: skip token documentation since it is auto-generated by CI pipeline."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["chip"]})
    r = h.start()
    assert r

    # Jump to docs
    r = h.goto("3.2 Generate documentation")
    assert r
    assert r.new_step == "3.2 Generate documentation"
    assert h.step == "3.2 Generate documentation"
    assert h.status == "running"

    # Skip: docs are auto-generated by GitHub Action on merge to main
    r = h.skip("Token documentation auto-generated by CI pipeline (token-docs.yml) on merge to main. Manual generation not needed.")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 5: Stop resume
# ===============================================================

def test_stop_resume(harness_factory):
    """Friday EOD: stop during token review for Select/RadioGroup form controls. Resume Monday morning."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["select", "radio_group"]})
    r = h.start()
    assert r

    # Approve token definitions for form control components
    r = h.approve({
        "tokens": {
            "color": {"input-border": "#CBD5E1", "input-focus": "#2563EB", "input-error": "#DC2626"},
            "spacing": {"input-padding-x": "12px", "input-padding-y": "8px"},
            "radius": {"input": "6px"},
        },
        "scope": "Form control tokens for Select and RadioGroup components",
    })
    assert r
    assert r.new_step == "1.2 Token review"
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    # Friday 5PM: stop during design review, team hasn't reviewed form tokens yet
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "1.2 Token review"

    # Monday 9AM: resume where we left off
    r = h.resume()
    assert r
    assert h.status == "waiting"
    assert h.step == "1.2 Token review"

    # Design team reviewed over weekend, tokens look good
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component with tokens"
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"


def test_s5_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.goto("3.2 Generate documentation")
    h.submit({})
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_s5_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_s5_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a non-stopped workflow."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    assert h.status == "waiting"

    r = h.resume()
    assert not r


# ===============================================================
# Scenario 6: Done reset
# ===============================================================

def test_done_reset_v2(harness_factory):
    """v1 token system done for Badge. Reset to start v2 rebrand with new brand colors."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["badge"]})
    r = h.start()
    assert r

    # Fast-track v1 Badge token system to completion
    r = h.goto("3.2 Generate documentation")
    assert r
    assert r.new_step == "3.2 Generate documentation"
    assert h.step == "3.2 Generate documentation"
    assert h.status == "running"

    r = h.submit({
        "docs": "v1 token reference: Badge uses color.primary for filled variant, color.muted for outline",
        "output": "docs/tokens-v1.mdx",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Verify v1 is complete
    status = h.get_status()
    assert status["status"] == "done"

    # Company rebrand: reset to define new brand token palette (purple instead of blue)
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define design tokens"
    assert h.status == "waiting"


# ===============================================================
# Scenario 7: Empty component list
# ===============================================================

def test_empty_component_list(harness_factory):
    """Token-only Figma audit: define and review tokens without building any components yet."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": []})
    r = h.start()
    assert r

    # Define tokens for Figma audit (no components to build, just validating token structure)
    r = h.approve({
        "tokens": {
            "color": {"brand-50": "#EFF6FF", "brand-500": "#3B82F6", "brand-900": "#1E3A5F"},
            "spacing": {"unit": "4px", "scale": "4/8/12/16/24/32/48/64"},
        },
        "purpose": "Figma token audit: validate naming convention and scale before component work begins",
    })
    assert r
    assert r.new_step == "1.2 Token review"
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    # Design systems team approves token naming convention
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Component loop")
    assert r

    # No components to build: loop exits immediately to consistency audit
    assert h.step == "3.1 Consistency audit"
    assert h.status == "running"


# ===============================================================
# Scenario 8: Goto
# ===============================================================

def test_goto(harness_factory):
    """Hotfix Breadcrumb link color: jump directly to implementation, then audit, then docs."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["breadcrumb"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define design tokens"
    assert h.status == "waiting"

    # Tokens already defined in a previous sprint, jump straight to component work
    r = h.goto("2.1 Implement component with tokens")
    assert r
    assert r.new_step == "2.1 Implement component with tokens"
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"

    # Breadcrumb implemented, jump to audit to verify token usage
    r = h.goto("3.1 Consistency audit")
    assert r
    assert r.new_step == "3.1 Consistency audit"
    assert h.step == "3.1 Consistency audit"
    assert h.status == "running"

    # Audit passed, jump to docs to update Breadcrumb token reference
    r = h.goto("3.2 Generate documentation")
    assert r
    assert r.new_step == "3.2 Generate documentation"
    assert h.step == "3.2 Generate documentation"
    assert h.status == "running"


# ===============================================================
# Scenario 9: Modify YAML
# ===============================================================

def test_modify_yaml_add_component(harness_factory):
    """Mid-sprint: add a WCAG contrast validation step to the Alert component token workflow."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["alert"]})
    r = h.start()
    assert r

    # Define alert tokens (info/success/warning/error semantic colors)
    r = h.approve({
        "tokens": {
            "color": {
                "alert-info-bg": "#DBEAFE", "alert-info-fg": "#1E40AF",
                "alert-error-bg": "#FEE2E2", "alert-error-fg": "#991B1B",
            },
        },
    })
    assert r
    assert r.new_step == "1.2 Token review"
    assert h.step == "1.2 Token review"

    # Approve and enter component loop
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Component loop")
    assert r
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"

    r = h.submit()
    assert r
    r = h.submit()
    assert r
    r = h.submit_goto("2.0 Component loop")
    assert r
    assert h.step == "3.1 Consistency audit"
    assert h.status == "running"

    # A11y team requests WCAG contrast validation step before docs
    modified_yaml = """name: Design-Token-Based Development Modified
description: Token with validation step

steps:
  - 1.1 Define design tokens:
      type: wait

  - 1.2 Token review:
      type: wait
      next:
        - if: "tokens approved"
          go: 1.3 Validate tokens
        - go: 1.1 Define design tokens

  - 1.3 Validate tokens

  - 2.0 Component loop:
      iterate: "components"
      children:
        - 2.1 Implement component with tokens
        - 2.2 Test component
        - 2.3 Component check:
            next:
              - if: "component correctly uses tokens"
                go: 2.0 Component loop
              - go: 2.1 Implement component with tokens

  - 3.1 Consistency audit:
      next:
        - if: "all components are consistent with tokens"
          go: 3.2 Generate documentation
        - go: 2.0 Component loop

  - 3.2 Generate documentation

  - Done:
      type: terminate
      reason: Design token system complete
"""

    h.reload_yaml(modified_yaml)

    # Jump to the newly added WCAG contrast validation step
    r = h.goto("1.3 Validate tokens")
    assert r
    assert r.new_step == "1.3 Validate tokens"
    assert h.step == "1.3 Validate tokens"
    assert h.status == "running"

    # Run axe-core contrast check on all alert token color pairs
    r = h.submit({
        "validation": "WCAG AA contrast check: info (7.2:1), error (8.1:1) - all pass",
        "tool": "axe-core 4.9",
    })
    assert r
    assert r.new_step == "2.1 Implement component with tokens"
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"


# ===============================================================
# Scenario 10: Back
# ===============================================================

def test_back(harness_factory):
    """DropdownMenu: go back to redefine shadow tokens after review, then back to fix implementation."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["dropdown_menu"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define design tokens"
    assert h.status == "waiting"

    # Define tokens including shadow for dropdown
    r = h.approve({
        "tokens": {
            "shadow": {"dropdown": "0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1)"},
            "color": {"dropdown-bg": "#FFFFFF", "dropdown-border": "#E2E8F0"},
            "radius": {"dropdown": "8px"},
            "spacing": {"dropdown-item-y": "8px", "dropdown-item-x": "12px"},
        },
    })
    assert r
    assert r.new_step == "1.2 Token review"
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    # Realized shadow token is too heavy for dropdown, go back to lighten it
    r = h.back()
    assert r
    assert r.new_step == "1.1 Define design tokens"
    assert h.step == "1.1 Define design tokens"
    assert h.status == "running"

    # Re-submit with lighter shadow token
    r = h.submit({
        "shadow_update": "Reduced dropdown shadow to 0 2px 4px rgba(0,0,0,0.06) for subtler appearance",
    })
    assert r
    assert r.new_step == "1.2 Token review"
    assert h.step == "1.2 Token review"
    assert h.status == "waiting"

    # Design team approves lighter shadow
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component with tokens"
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"

    # Implement DropdownMenu using Radix UI + token CSS vars
    r = h.submit({
        "component": "DropdownMenu",
        "file": "src/components/DropdownMenu/DropdownMenu.tsx",
        "dependencies": ["@radix-ui/react-dropdown-menu"],
        "tokens_used": ["shadow.dropdown", "color.dropdown-bg", "color.dropdown-border", "radius.dropdown"],
    })
    assert r
    assert r.new_step == "2.2 Test component"
    assert h.step == "2.2 Test component"

    # Tests reveal z-index issue, go back to fix implementation
    r = h.back()
    assert r
    assert r.new_step == "2.1 Implement component with tokens"
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"


# ===============================================================
# Multi-dimension: Loop counter and cleanup
# ===============================================================

def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["a", "b", "c"]})
    _walk_to_loop(h)

    loop_info = h.state.loop_state["2.0 Component loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_component(h)
    h.submit_goto("2.0 Component loop")

    loop_info = h.state.loop_state["2.0 Component loop"]
    assert loop_info["i"] == 1

    _do_one_component(h)
    h.submit_goto("2.0 Component loop")

    loop_info = h.state.loop_state["2.0 Component loop"]
    assert loop_info["i"] == 2


def test_loop_cleanup_on_exit(harness_factory):
    """Loop state is cleaned up after all iterations complete."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["only"]})
    _walk_to_loop(h)

    _do_one_component(h)
    h.submit_goto("2.0 Component loop")

    assert h.step == "3.1 Consistency audit"
    assert "2.0 Component loop" not in h.state.loop_state


def test_loop_data_per_iteration(harness_factory):
    """Each iteration overwrites step data keys but data persists."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["a", "b"]})
    _walk_to_loop(h)

    h.submit({"component": "comp_a"})
    h.submit({})
    h.submit_goto("2.0 Component loop")

    h.submit({"component": "comp_b"})
    data = h.state.data
    assert data["2.1 Implement component with tokens"]["component"] == "comp_b"


# ===============================================================
# Multi-dimension: Node archives per iteration
# ===============================================================

def test_node_archives_per_iteration(harness_factory):
    """Archive node accumulates one row per loop iteration."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["a", "b", "c"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Implement component with tokens",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"comp_name": "string"}},
            archive={"table": "dt_components"},
        ),
    )

    for i in range(3):
        h.submit({"comp_name": f"comp_{i}"})
        h.submit({})
        h.submit_goto("2.0 Component loop")

    rows = h.get_archived_rows("dt_components")
    assert len(rows) == 3


# ===============================================================
# Multi-dimension: Cross-executor preserves loop
# ===============================================================

def test_cross_executor_preserves_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state intact."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["a", "b", "c"]})
    _walk_to_loop(h)

    _do_one_component(h)
    h.submit_goto("2.0 Component loop")

    # Mid iteration 2
    h.submit({"component": "mid_loop"})
    assert h.step == "2.2 Test component"

    h.new_executor()

    assert h.step == "2.2 Test component"
    loop_info = h.state.loop_state["2.0 Component loop"]
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.approve({})
    assert h.step == "1.2 Token review"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()
    assert h.step == "1.2 Token review"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.approve({"tokens": "defined"})

    h.save_checkpoint("at_token_review")

    h.approve()
    h.submit_goto("2.0 Component loop")
    assert h.step == "2.1 Implement component with tokens"

    restored = h.load_checkpoint("at_token_review")
    assert restored is not None
    assert restored.current_step == "1.2 Token review"
    assert "1.1 Define design tokens" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.goto("2.1 Implement component with tokens")
    assert h.step == "2.1 Implement component with tokens"

    r = h.retry()
    assert r
    assert h.step == "2.1 Implement component with tokens"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.goto("3.2 Generate documentation")
    h.submit({})
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})

    for _ in range(3):
        h.start()
        h.approve({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define design tokens"


def test_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.approve({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.goto("3.2 Generate documentation")
    h.submit({})
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.goto("2.1 Implement component with tokens")
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_approve_on_non_waiting_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.goto("2.1 Implement component with tokens")
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_non_waiting_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.goto("2.1 Implement component with tokens")
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_wait_step_rejects_submit(harness_factory):
    """At a wait step (1.1), submit is rejected with 'waiting' message."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    assert h.step == "1.1 Define design tokens"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_history_records_transition_steps(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["x"]})
    h.start()
    h.approve({})
    h.approve()
    h.submit_goto("2.0 Component loop")

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["btn"]})
    h.start()
    h.approve({"tokens": "colors, spacing"})
    h.approve()
    h.submit_goto("2.0 Component loop")

    h.register_node(
        "2.1 Implement component with tokens",
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
    h = harness_factory("p2-design-token.yaml", loop_data={"components": ["btn"]})
    h.start()

    h.register_node(
        "1.1 Define design tokens",
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
