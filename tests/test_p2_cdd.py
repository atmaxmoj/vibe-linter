"""Test scenarios for CDD workflow (p2-cdd.yaml).

Tests the Component-Driven Development workflow including:
- Planning phase (break page, define interfaces)
- Component loop with visual check 2-way branching
- Integration phase (compose, e2e, PR review wait)
- State transitions, gotos, stops/resumes, and hot-reload

Workflow structure:
  1.1 Break page into components
  1.2 Define component interfaces
  2.0 Component loop (iterate: components)
    2.1 Implement component
    2.2 Write component tests
    2.3 Visual check (LLM 2-way: pass->2.0, fail->2.1)
  3.1 Compose page from components
  3.2 End-to-end testing
  3.3 PR review (wait, LLM: approved->Done, else->2.0)
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
    h.submit({"breakdown": "components identified"})
    h.submit({"interfaces": "props defined"})
    assert h.step == "2.1 Implement component"
    assert h.status == "running"


def _do_one_component(h):
    """Complete one implement-test-check cycle ending at visual check."""
    h.submit({"component": "impl"})
    h.submit({"tests": "pass"})
    assert h.step == "2.3 Visual check"


def _complete_loop_and_finish(h, n_components):
    """From inside the loop, exhaust all iterations and reach Done."""
    for _i in range(n_components):
        if h.step != "2.1 Implement component":
            h.submit_goto("2.0 Component loop")
        _do_one_component(h)
        h.submit_goto("2.0 Component loop")
    assert h.step == "3.1 Compose page from components"
    h.submit({"page": "composed"})
    h.submit({"e2e": "pass"})
    assert h.step == "3.3 PR review"
    assert h.status == "waiting"
    h.approve()
    h.submit_goto("Done")
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 1: Full walkthrough (5 components)
# ===============================================================

def test_new_page_5_components(harness_factory):
    """Build e-commerce product listing page: Header, SearchBar, ProductCard, FilterSidebar, CartModal."""
    h = harness_factory(
        "p2-cdd.yaml", loop_data={"components": ["header", "search_bar", "product_card", "filter_sidebar", "cart_modal"]}
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Break page into components"
    assert h.status == "running"

    # Break down the product listing page into isolated components
    r = h.submit({
        "page": "Product Listing Page (/products)",
        "components": [
            {"name": "Header", "type": "organism", "description": "Logo, nav links, cart icon with badge"},
            {"name": "SearchBar", "type": "molecule", "description": "Text input with debounced autocomplete"},
            {"name": "ProductCard", "type": "molecule", "description": "Image, title, price, add-to-cart button"},
            {"name": "FilterSidebar", "type": "organism", "description": "Category checkboxes, price range slider, brand filter"},
            {"name": "CartModal", "type": "organism", "description": "Slide-out panel with line items, quantity controls, checkout CTA"},
        ],
        "layout": "CSS Grid: sidebar 280px | main auto, header full-width sticky",
    })
    assert r
    assert r.new_step == "1.2 Define component interfaces"
    assert h.step == "1.2 Define component interfaces"
    assert h.status == "running"

    # Define TypeScript interfaces for each component
    r = h.submit({
        "interfaces": {
            "Header": {"props": {"cartItemCount": "number", "onCartClick": "() => void", "currentUser": "User | null"}},
            "SearchBar": {"props": {"onSearch": "(query: string) => void", "placeholder": "string", "debounceMs": "number"}},
            "ProductCard": {"props": {"product": "Product", "onAddToCart": "(productId: string) => void", "isInCart": "boolean"}},
            "FilterSidebar": {"props": {"filters": "FilterState", "onFilterChange": "(filters: FilterState) => void", "categories": "Category[]"}},
            "CartModal": {"props": {"isOpen": "boolean", "items": "CartItem[]", "onClose": "() => void", "onCheckout": "() => void"}},
        },
        "shared_types": "Product, CartItem, FilterState, Category defined in types/index.ts",
    })
    assert r
    assert r.new_step == "2.1 Implement component"
    assert h.step == "2.1 Implement component"
    assert h.status == "running"

    # Component 1: Header with cart badge
    r = h.submit({
        "component": "Header",
        "file": "src/components/Header/Header.tsx",
        "implementation": "Sticky header with flexbox layout, cart icon uses Badge from design system, responsive hamburger menu below 768px",
        "tokens_used": ["color.primary", "spacing.md", "font.heading"],
    })
    assert r
    assert r.new_step == "2.2 Write component tests"
    assert h.step == "2.2 Write component tests"

    r = h.submit({
        "test_file": "src/components/Header/Header.test.tsx",
        "tests": [
            "renders logo and navigation links",
            "displays cart badge with correct count",
            "calls onCartClick when cart icon clicked",
            "shows hamburger menu on mobile viewport",
        ],
        "coverage": "94%",
    })
    assert r
    assert r.new_step == "2.3 Visual check"
    assert h.step == "2.3 Visual check"

    # Visual check passes for Header
    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component"
    assert h.step == "2.1 Implement component"

    # Components 2-5: SearchBar, ProductCard, FilterSidebar, CartModal
    for _comp in ["search_bar", "product_card", "filter_sidebar", "cart_modal"]:
        r = h.submit()
        assert r
        r = h.submit()
        assert r
        r = h.submit_goto("2.0 Component loop")
        assert r

    # After 5 iterations, should exit loop and go to integration
    assert h.step == "3.1 Compose page from components"
    assert h.status == "running"

    r = h.submit({
        "page": "ProductListingPage",
        "file": "src/pages/ProductListingPage.tsx",
        "composition": "Grid layout with FilterSidebar left, ProductCard grid right, SearchBar in Header, CartModal as portal overlay",
        "state_management": "useProductFilters hook connects SearchBar + FilterSidebar to ProductCard grid via React context",
    })
    assert r
    assert r.new_step == "3.2 End-to-end testing"
    assert h.step == "3.2 End-to-end testing"

    r = h.submit({
        "e2e_framework": "Playwright",
        "scenarios": [
            "user searches for 'wireless mouse' and sees filtered results",
            "user filters by price range $20-$50 and category 'Electronics'",
            "user adds product to cart, badge updates, modal shows correct item",
            "user removes item from cart modal, badge decrements",
            "responsive: sidebar collapses to drawer on mobile, grid goes single-column",
        ],
        "result": "all 5 scenarios pass across Chrome, Firefox, Safari",
    })
    assert r
    assert r.new_step == "3.3 PR review"
    assert h.step == "3.3 PR review"
    assert h.status == "waiting"

    # PR approved: WAIT+LLM step needs approve() then submit_goto()
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["btn"]})
    h.start()

    h.submit({"breakdown": "1 component"})
    data = h.state.data
    assert "1.1 Break page into components" in data
    assert data["1.1 Break page into components"]["breakdown"] == "1 component"

    h.submit({"interfaces": "props for btn"})
    data = h.state.data
    assert "1.2 Define component interfaces" in data
    assert data["1.2 Define component interfaces"]["interfaces"] == "props for btn"

    # Now inside loop
    h.submit({"component": "button"})
    data = h.state.data
    assert "2.1 Implement component" in data
    assert data["2.1 Implement component"]["component"] == "button"


def test_s1_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["c1"]})
    h.start()
    h.submit({})
    h.submit({})
    # Loop: implement, test, visual check
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Component loop")
    # After 1 component, loop exits
    assert h.step == "3.1 Compose page from components"
    h.submit({})
    h.submit({})
    assert h.step == "3.3 PR review"
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


def test_s1_cross_executor_at_planning(harness_factory):
    """Close executor at planning phase, reopen, continue."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.submit({"breakdown": "parts"})
    assert h.step == "1.2 Define component interfaces"

    h.new_executor()

    assert h.step == "1.2 Define component interfaces"
    assert h.status == "running"

    r = h.submit({"interfaces": "defined"})
    assert r
    assert h.step == "2.1 Implement component"


def test_s1_cross_executor_at_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state preserved."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["a", "b"]})
    _walk_to_loop(h)

    h.submit({"component": "a_impl"})
    assert h.step == "2.2 Write component tests"

    h.new_executor()

    assert h.step == "2.2 Write component tests"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Component loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_s1_node_validates_component(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["btn"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Implement component",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("component") else "must include component name",
        ),
    )

    # Bad data
    r = h.submit({"notes": "forgot the name"})
    assert not r
    assert "rejected" in r.message.lower()

    # Good data
    r = h.submit({"component": "button"})
    assert r
    assert r.new_step == "2.2 Write component tests"


def test_s1_node_archives_components(harness_factory):
    """Archive node writes submitted data to SQLite table."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["a", "b"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Implement component",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"name": "string", "type": "string"}},
            archive={"table": "components_built"},
        ),
    )

    h.submit({"name": "header", "type": "layout"})
    h.submit({})  # test
    h.submit_goto("2.0 Component loop")  # visual -> loop
    h.submit({"name": "card", "type": "display"})

    rows = h.get_archived_rows("components_built")
    assert len(rows) == 2
    assert rows[0]["name"] == "header"
    assert rows[1]["name"] == "card"


# ===============================================================
# Scenario 2: Style fix 5 rounds
# ===============================================================

def test_style_fix_5_rounds(harness_factory):
    """DatePicker component visual check fails 5 times: z-index, shadow, alignment, animation, focus ring."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["datepicker"]})
    r = h.start()
    assert r

    # Jump to visual check
    r = h.goto("2.3 Visual check")
    assert r
    assert r.new_step == "2.3 Visual check"
    assert h.step == "2.3 Visual check"
    assert h.status == "running"

    # Round 1: dropdown renders behind the modal overlay
    r = h.submit_goto("2.1 Implement component")
    assert r
    assert r.new_step == "2.1 Implement component"
    assert h.step == "2.1 Implement component"

    r = h.submit({
        "component": "DatePicker",
        "fix": "Set z-index: 9999 on .datepicker-dropdown, use React Portal to escape stacking context",
        "issue_resolved": "z-index conflict with modal overlay",
    })
    assert r
    r = h.submit()
    assert r
    assert h.step == "2.3 Visual check"

    # Round 2: box-shadow too aggressive on light theme
    # Round 3: calendar grid misaligned on RTL locales
    # Round 4: open/close animation janky (60fps drops to 24fps)
    # Round 5: focus ring invisible on dark theme
    for i, issue in enumerate([
        "Replaced hard-coded box-shadow with token shadow.md, reduces visual weight on light theme",
        "Added dir='auto' to calendar grid, swapped margin-left to margin-inline-start for RTL support",
        "Switched from height transition to transform: scaleY() with will-change hint, solid 60fps now",
    ], start=2):
        r = h.submit_goto("2.1 Implement component")
        assert r
        r = h.submit({"component": "DatePicker", "fix": issue, "attempt": i})
        assert r
        r = h.submit()
        assert r
        assert h.step == "2.3 Visual check"

    # Round 5: focus ring invisible on dark theme
    r = h.submit_goto("2.1 Implement component")
    assert r
    r = h.submit({
        "component": "DatePicker",
        "fix": "Changed focus ring from outline: 2px solid blue to outline: 2px solid var(--color-focus-ring) with 2px offset, visible on both themes",
        "attempt": 5,
        "visual_qa": "Pixel-perfect match with Figma spec on light, dark, and high-contrast themes",
    })
    assert r
    r = h.submit()
    assert r
    assert h.step == "2.3 Visual check"

    # This time it passes - but goto didn't set up loop state,
    # so first submit_goto to loop header initializes the loop (i=0, n=1)
    # which moves to first child. We need to complete one iteration then exit.
    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component"
    assert h.step == "2.1 Implement component"

    # Complete iteration 0 and re-enter loop to exit (i=1 == n=1)
    r = h.submit()
    assert r
    r = h.submit()
    assert r
    r = h.submit_goto("2.0 Component loop")
    assert r
    assert h.step == "3.1 Compose page from components"
    assert h.status == "running"


def test_s2_data_has_all_attempts(harness_factory):
    """All 5 submit attempts store data (last wins per step key)."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["btn"]})
    h.start()
    h.goto("2.1 Implement component")

    for i in range(5):
        h.submit({"component": f"attempt_{i}"})
        if h.step != "2.1 Implement component":
            h.goto("2.1 Implement component")

    data = h.state.data
    assert "2.1 Implement component" in data


def test_s2_history_depth(harness_factory):
    """5 rounds of failing produce many history entries."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["btn"]})
    h.start()
    h.goto("2.3 Visual check")

    for _ in range(5):
        h.submit_goto("2.1 Implement component")
        h.submit({})
        h.submit({})

    history = h.get_history(100)
    assert len(history) >= 15


def test_s2_cross_executor_mid_retry(harness_factory):
    """Close executor after 3 fails, reopen, continue from same step."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["btn"]})
    h.start()
    h.goto("2.3 Visual check")

    for _ in range(3):
        h.submit_goto("2.1 Implement component")
        h.submit({})
        h.submit({})
    assert h.step == "2.3 Visual check"

    h.new_executor()
    assert h.step == "2.3 Visual check"
    assert h.status == "running"

    h.submit_goto("2.1 Implement component")
    assert h.step == "2.1 Implement component"


# ===============================================================
# Scenario 3: PR rejected back
# ===============================================================

def test_pr_rejected_back(harness_factory):
    """PR rejected for checkout form: accessibility violations found, fix and re-submit."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["checkout_form"]})
    r = h.start()
    assert r

    # Jump to PR review - goto always sets status=running
    r = h.goto("3.3 PR review")
    assert r
    assert r.new_step == "3.3 PR review"
    assert h.step == "3.3 PR review"
    assert h.status == "running"

    # PR feedback: form inputs missing labels, color contrast ratio fails WCAG AA
    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component"
    assert h.step == "2.1 Implement component"
    assert h.status == "running"

    # Fix the CheckoutForm: add aria-labels, fix contrast ratios
    r = h.submit({
        "component": "CheckoutForm",
        "fixes": [
            "Added <label htmlFor> to all input fields (name, email, card number, expiry, CVV)",
            "Changed placeholder text color from #999 to #595959 for 4.5:1 contrast ratio",
            "Added aria-describedby linking error messages to their input fields",
            "Added role='alert' to inline validation errors for screen reader announcement",
        ],
    })
    assert r
    r = h.submit()
    assert r
    r = h.submit_goto("2.0 Component loop")
    assert r

    # After 1 component in loop, exits to integration
    assert h.step == "3.1 Compose page from components"
    assert h.status == "running"

    r = h.submit()
    assert r
    r = h.submit()
    assert r
    assert h.step == "3.3 PR review"
    assert h.status == "waiting"

    # This time PR passes: all a11y issues resolved, Lighthouse score 100
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_s3_pr_reject_preserves_data(harness_factory):
    """Reject does not modify state.data."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.submit({"breakdown": "parts"})
    h.submit({"interfaces": "defined"})
    h.submit({"component": "x"})
    h.submit({"tests": "pass"})
    h.submit_goto("2.0 Component loop")
    h.submit({})
    h.submit({})
    assert h.step == "3.3 PR review"
    assert h.status == "waiting"

    data_before = dict(h.state.data)
    h.reject("needs fixes")
    data_after = h.state.data
    assert data_before == data_after


def test_s3_pr_reject_adds_history(harness_factory):
    """Reject action appears in history."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Component loop")
    h.submit({})
    h.submit({})
    assert h.step == "3.3 PR review"
    h.reject("bad PR")

    history = h.get_history(30)
    reject_entries = [e for e in history if e["action"] == "reject"]
    assert len(reject_entries) >= 1
    assert reject_entries[0]["data"] == "bad PR"


# ===============================================================
# Scenario 4: Empty component list
# ===============================================================

def test_empty_component_list(harness_factory):
    """Static landing page with no interactive components: pure HTML/CSS, skip component loop entirely."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": []})
    r = h.start()
    assert r

    # Planning reveals this is a pure static marketing page - no React components needed
    r = h.submit({
        "page": "Company About Page",
        "analysis": "Static content only: hero section, team photos, office gallery. No interactive elements. Pure HTML + Tailwind.",
    })
    assert r
    r = h.submit({
        "interfaces": "No component interfaces needed - all content is static HTML rendered server-side",
    })
    assert r

    # Loop should exit immediately since list is empty
    assert h.step == "3.1 Compose page from components"
    assert h.status == "running"


# ===============================================================
# Scenario 5: Switch ticket stop reset
# ===============================================================

def test_switch_ticket_stop_reset(harness_factory):
    """Building admin settings page, P0 bug arrives mid-sprint: stop, reset, start new ticket."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["settings_sidebar", "settings_panel"]})
    r = h.start()
    assert r

    # Started building the admin settings page
    r = h.submit({
        "page": "Admin Settings (/admin/settings)",
        "components": ["SettingsSidebar", "SettingsPanel"],
        "ticket": "JIRA-2847: Admin settings page redesign",
    })
    assert r
    r = h.submit({
        "interfaces": {
            "SettingsSidebar": {"props": {"sections": "SettingsSection[]", "activeSection": "string"}},
            "SettingsPanel": {"props": {"section": "SettingsSection", "onSave": "(data: FormData) => void"}},
        },
    })
    assert r
    assert h.step == "2.1 Implement component"

    r = h.submit({
        "component": "SettingsSidebar",
        "file": "src/components/Admin/SettingsSidebar.tsx",
        "implementation": "Vertical nav with section icons, active state highlight, collapsible sub-sections",
    })
    assert r
    assert r.new_step == "2.2 Write component tests"
    assert h.step == "2.2 Write component tests"

    # P0 bug: payment processing broken in production. Drop everything.
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Write component tests"

    # Reset to start working on the P0 hotfix ticket instead
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Break page into components"
    assert h.status == "running"


def test_s5_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.goto("3.3 PR review")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_s5_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_s5_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ===============================================================
# Scenario 6: Skip component
# ===============================================================

def test_skip_component(harness_factory):
    """Dashboard page: build Chart and Table from scratch, skip Breadcrumb (use existing library component)."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["chart", "breadcrumb", "data_table"]})
    r = h.start()
    assert r

    # Go through planning to properly enter loop via loop header
    r = h.submit({
        "page": "Analytics Dashboard",
        "components": ["RevenueChart", "Breadcrumb", "DataTable"],
    })
    assert r
    r = h.submit({
        "interfaces": {
            "RevenueChart": {"props": {"data": "TimeSeriesData[]", "period": "'day' | 'week' | 'month'"}},
            "Breadcrumb": {"props": "using @shadcn/ui Breadcrumb, no custom props needed"},
            "DataTable": {"props": {"columns": "ColumnDef[]", "data": "Row[]", "onSort": "(col: string) => void"}},
        },
    })
    assert r
    assert h.step == "2.1 Implement component"
    assert h.status == "running"

    # Component 1: RevenueChart - build from scratch with Recharts
    r = h.submit({
        "component": "RevenueChart",
        "file": "src/components/Dashboard/RevenueChart.tsx",
        "implementation": "Line chart with Recharts, supports day/week/month toggle, responsive container, tooltip with formatted currency",
    })
    assert r
    r = h.submit({
        "tests": ["renders chart with sample data", "toggles period correctly", "shows tooltip on hover"],
    })
    assert r
    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component"
    assert h.step == "2.1 Implement component"

    # Component 2: Breadcrumb - skip, already exists in shadcn/ui
    r = h.skip("Using @shadcn/ui Breadcrumb component directly, no custom implementation needed")
    assert r
    assert r.new_step == "2.2 Write component tests"
    assert h.step == "2.2 Write component tests"

    r = h.skip("Breadcrumb is tested upstream in shadcn/ui, only integration tests needed later")
    assert r
    assert r.new_step == "2.3 Visual check"
    assert h.step == "2.3 Visual check"

    # skip() on LLM step triggers "needs judgment" and stays.
    # Use submit_goto to properly go through loop header and increment counter.
    r = h.submit_goto("2.0 Component loop")
    assert r
    assert r.new_step == "2.1 Implement component"
    assert h.step == "2.1 Implement component"

    # Component 3: DataTable - build custom sortable table
    r = h.submit({
        "component": "DataTable",
        "file": "src/components/Dashboard/DataTable.tsx",
        "implementation": "Virtualized table with TanStack Table, column sorting, sticky header, row selection checkboxes",
    })
    assert r
    r = h.submit({
        "tests": ["renders columns from definition", "sorts ascending/descending on header click", "selects rows with checkbox"],
    })
    assert r
    r = h.submit_goto("2.0 Component loop")
    assert r

    # Exit loop
    assert h.step == "3.1 Compose page from components"
    assert h.status == "running"


def test_s6_skip_records_reason(harness_factory):
    """Skip reason appears in history data field."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()

    h.skip("skip planning")
    history = h.get_history(5)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "skip planning"


# ===============================================================
# Scenario 7: Back
# ===============================================================

def test_back(harness_factory):
    """Building notification widget: realize interface needs events prop, go back to fix."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["notification_widget"]})
    r = h.start()
    assert r

    r = h.submit({
        "page": "Global Notification System",
        "components": ["NotificationWidget - toast container with stacking, auto-dismiss, action buttons"],
    })
    assert r
    assert r.new_step == "1.2 Define component interfaces"
    assert h.step == "1.2 Define component interfaces"

    # Go back: realized we need to split NotificationWidget into Toast + ToastContainer
    r = h.back()
    assert r
    assert r.new_step == "1.1 Break page into components"
    assert h.step == "1.1 Break page into components"
    assert h.status == "running"

    # Continue forward with corrected breakdown
    r = h.submit()
    assert r
    r = h.submit()
    assert r
    assert h.step == "2.1 Implement component"

    r = h.submit({
        "component": "NotificationWidget",
        "file": "src/components/Notifications/NotificationWidget.tsx",
        "implementation": "Fixed-position container using Framer Motion AnimatePresence for enter/exit, max 5 visible toasts",
    })
    assert r
    assert r.new_step == "2.2 Write component tests"
    assert h.step == "2.2 Write component tests"

    # Go back: implementation needs useReducer instead of useState for complex state
    r = h.back()
    assert r
    assert r.new_step == "2.1 Implement component"
    assert h.step == "2.1 Implement component"
    assert h.status == "running"


# ===============================================================
# Scenario 8: Modify YAML
# ===============================================================

def test_modify_yaml_add_component(harness_factory):
    """Mid-sprint SOP change: team mandates ESLint + Stylelint step before composition after finding inconsistent imports."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["avatar"]})
    r = h.start()
    assert r

    # Go through planning to properly initialize loop via loop header
    r = h.submit({
        "page": "User Profile Page",
        "components": ["Avatar - circular image with fallback initials, online status indicator"],
    })
    assert r
    r = h.submit({
        "interfaces": {"Avatar": {"props": {"src": "string | null", "name": "string", "size": "'sm' | 'md' | 'lg'", "isOnline": "boolean"}}},
    })
    assert r
    assert h.step == "2.1 Implement component"

    # Complete Avatar component
    r = h.submit({
        "component": "Avatar",
        "implementation": "CSS aspect-ratio circle, <img> with onError fallback to initials, green dot indicator positioned absolute bottom-right",
    })
    assert r
    r = h.submit({
        "tests": ["renders image when src provided", "shows initials when image fails to load", "displays online indicator"],
    })
    assert r
    r = h.submit_goto("2.0 Component loop")
    assert r

    assert h.step == "3.1 Compose page from components"
    assert h.status == "running"

    # Tech lead adds mandatory linting step after finding wildcard imports in Avatar component
    modified_yaml = """name: CDD Development Modified
description: CDD with added linting step

steps:
  - 1.1 Break page into components

  - 1.2 Define component interfaces

  - 2.0 Component loop:
      iterate: "components"
      children:
        - 2.1 Implement component
        - 2.2 Write component tests
        - 2.3 Visual check:
            next:
              - if: "component looks correct visually"
                go: 2.0 Component loop
              - go: 2.1 Implement component

  - 2.9 Lint all components

  - 3.1 Compose page from components

  - 3.2 End-to-end testing

  - 3.3 PR review:
      type: wait
      next:
        - if: "PR approved"
          go: Done
        - go: 2.0 Component loop

  - Done:
      type: terminate
      reason: All components built and PR approved
"""

    h.reload_yaml(modified_yaml)

    # After reload, the loop state was cleared when loop exited.
    r = h.goto("2.9 Lint all components")
    assert r
    assert r.new_step == "2.9 Lint all components"
    assert h.step == "2.9 Lint all components"
    assert h.status == "running"

    # Run ESLint + Stylelint on all components
    r = h.submit({
        "eslint": "Fixed 3 issues: wildcard import in Avatar, missing React.memo on ProfileCard, unused prop 'className'",
        "stylelint": "Fixed 2 issues: shorthand property override in Avatar.module.css, non-standard color function",
        "result": "0 errors, 0 warnings after fixes",
    })
    assert r
    assert r.new_step == "3.1 Compose page from components"
    assert h.step == "3.1 Compose page from components"
    assert h.status == "running"


# ===============================================================
# Scenario 9: Done next ticket
# ===============================================================

def test_done_next_ticket(harness_factory):
    """Landing page hero section complete and shipped, verify workflow is finalized."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["hero_section"]})
    r = h.start()
    assert r

    # Fast-track to done - goto sets status=running, not waiting
    r = h.goto("3.3 PR review")
    assert r
    assert r.new_step == "3.3 PR review"
    assert h.step == "3.3 PR review"
    assert h.status == "running"

    # PR already approved via GitHub, finalize workflow
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Verify status shows completed
    status = h.get_status()
    assert status["status"] == "done"
    assert status["current_step"] == "Done"


# ===============================================================
# Scenario 10: Goto PR
# ===============================================================

def test_goto_pr(harness_factory):
    """Quick copy change on existing Tooltip component: skip all building, jump straight to PR review."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["tooltip"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Break page into components"

    # Minor copy update to existing Tooltip: just need PR review, skip everything else
    r = h.goto("3.3 PR review")
    assert r
    assert r.new_step == "3.3 PR review"
    assert h.step == "3.3 PR review"
    assert h.status == "running"

    # Trivial change approved, ship it
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Multi-dimension: Loop counter and cleanup
# ===============================================================

def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["a", "b", "c"]})
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
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["only"]})
    _walk_to_loop(h)

    _do_one_component(h)
    h.submit_goto("2.0 Component loop")

    assert h.step == "3.1 Compose page from components"
    assert "2.0 Component loop" not in h.state.loop_state


def test_loop_data_per_iteration(harness_factory):
    """Each iteration overwrites step data keys but data persists."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["a", "b"]})
    _walk_to_loop(h)

    h.submit({"component": "comp_a"})
    h.submit({})
    h.submit_goto("2.0 Component loop")

    h.submit({"component": "comp_b"})
    data = h.state.data
    assert data["2.1 Implement component"]["component"] == "comp_b"


# ===============================================================
# Multi-dimension: Node archives per iteration
# ===============================================================

def test_node_archives_per_iteration(harness_factory):
    """Archive node accumulates one row per loop iteration."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["a", "b", "c"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Implement component",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"comp_name": "string"}},
            archive={"table": "cdd_components"},
        ),
    )

    for i in range(3):
        h.submit({"comp_name": f"comp_{i}"})
        h.submit({})
        h.submit_goto("2.0 Component loop")

    rows = h.get_archived_rows("cdd_components")
    assert len(rows) == 3


# ===============================================================
# Multi-dimension: Cross-executor preserves loop
# ===============================================================

def test_cross_executor_preserves_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state intact."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["a", "b", "c"]})
    _walk_to_loop(h)

    _do_one_component(h)
    h.submit_goto("2.0 Component loop")

    # Mid iteration 2
    h.submit({"component": "mid_loop"})
    assert h.step == "2.2 Write component tests"

    h.new_executor()

    assert h.step == "2.2 Write component tests"
    loop_info = h.state.loop_state["2.0 Component loop"]
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


# ===============================================================
# Multi-dimension: Stop/resume at wait step
# ===============================================================

def test_stop_resume_at_pr_review(harness_factory):
    """Stop at PR review wait step, resume restores waiting."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Component loop")
    h.submit({})
    h.submit({})
    assert h.step == "3.3 PR review"
    assert h.status == "waiting"

    h.stop()
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"
    assert h.step == "3.3 PR review"


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Define component interfaces"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()
    assert h.step == "1.2 Define component interfaces"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.submit({"breakdown": "parts"})
    h.submit({"interfaces": "defined"})

    h.save_checkpoint("at_loop_entry")

    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Component loop")
    assert h.step == "3.1 Compose page from components"

    restored = h.load_checkpoint("at_loop_entry")
    assert restored is not None
    assert restored.current_step == "2.1 Implement component"
    assert "1.2 Define component interfaces" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    assert h.step == "1.1 Break page into components"

    r = h.retry()
    assert r
    assert h.step == "1.1 Break page into components"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.goto("3.3 PR review")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Break page into components"


def test_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.goto("3.3 PR review")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_approve_on_non_waiting_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_non_waiting_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_wait_step_rejects_submit(harness_factory):
    """At a wait step (3.3), submit is rejected with 'waiting' message."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Component loop")
    h.submit({})
    h.submit({})
    assert h.step == "3.3 PR review"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_history_records_transition_steps(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["x"]})
    h.start()
    h.submit({})
    h.submit({})

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["btn"]})
    h.start()
    h.submit({"breakdown": "components identified"})
    h.submit({"interfaces": "props defined"})

    h.register_node(
        "2.1 Implement component",
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
    h = harness_factory("p2-cdd.yaml", loop_data={"components": ["btn"]})
    h.start()

    h.register_node(
        "1.1 Break page into components",
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
