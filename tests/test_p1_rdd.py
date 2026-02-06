"""Test scenarios for RDD SOP workflow (p1-rdd.yaml).

Tests the complete RDD (README-Driven Development) workflow including:
- README draft and review with rejection loop
- Implementation, tests, and test execution
- Alignment check with 3-way fallback (align->review, minor fixes->impl, else->README)
- Final review with approval/rejection

Workflow structure:
  1.1 Write README draft
  1.2 README review (wait, LLM: approved->2.1, else->1.1)
  2.1 Implement code
  2.2 Write tests
  2.3 Run tests
  3.1 Align code with README (LLM: aligns->3.2, minor fixes->2.1, else->1.1)
  3.2 Final review (wait, LLM: approved->Done, else->2.1)
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

# ─── Helpers ───


def _walk_to_readme_review(h):
    """Common helper: start -> submit 1.1 -> arrive at 1.2 (waiting)."""
    h.start()
    h.submit({"readme": "# Project\nOverview"})
    assert h.step == "1.2 README review"
    assert h.status == "waiting"


def _enter_implementation(h):
    """Common helper: get past README review into implementation phase."""
    _walk_to_readme_review(h)
    h.approve()
    h.submit_goto("2.1 Implement code")
    assert h.step == "2.1 Implement code"
    assert h.status == "running"


def _walk_to_alignment(h):
    """Common helper: get through implementation to alignment check."""
    _enter_implementation(h)
    h.submit({"code": "main.py"})
    h.submit({"tests": "test_main.py"})
    h.submit({"result": "all pass"})
    assert h.step == "3.1 Align code with README"
    assert h.status == "running"


# ===============================================================
# Scenario 1: Linear walkthrough (original)
# ===============================================================

def test_scenario_1_linear_walkthrough(harness_factory):
    """Build a CLI password manager: README-first, then implement to match the docs."""
    h = harness_factory("p1-rdd.yaml")
    r = h.start()
    assert r

    # Phase 1: README
    assert h.step == "1.1 Write README draft"
    assert h.status == "running"

    r = h.submit({
        "readme": (
            "# vaultctl -- CLI Password Manager\n\n"
            "## Installation\n"
            "```bash\npip install vaultctl\n```\n\n"
            "## Usage\n"
            "```bash\n"
            "vaultctl init              # Create encrypted vault\n"
            "vaultctl add github        # Add a new entry\n"
            "vaultctl get github        # Copy password to clipboard\n"
            "vaultctl list              # List all entries\n"
            "vaultctl export --json     # Export vault as JSON\n"
            "```\n\n"
            "## Security\n"
            "- AES-256-GCM encryption at rest\n"
            "- Master password derived via Argon2id\n"
            "- Clipboard auto-clear after 30 seconds\n"
        ),
        "file": "README.md",
    })
    assert r
    assert r.new_step == "1.2 README review"
    assert h.step == "1.2 README review"
    assert h.status == "waiting"

    # Wait step arrival: submit is rejected
    r = h.submit({})
    assert not r
    assert "waiting" in r.message.lower()

    # README approved -> implementation (WAIT+LLM: approve first, then submit_goto)
    r = h.approve()
    assert r
    assert h.step == "1.2 README review"
    assert h.status == "running"

    r = h.submit_goto("2.1 Implement code")
    assert r
    assert r.new_step == "2.1 Implement code"
    assert h.step == "2.1 Implement code"
    assert h.status == "running"

    # Phase 2: Implementation
    r = h.submit({
        "files_created": [
            "vaultctl/cli.py",
            "vaultctl/vault.py",
            "vaultctl/crypto.py",
        ],
        "summary": "CLI with click, AES-256-GCM via cryptography lib, Argon2id key derivation",
        "commands_implemented": ["init", "add", "get", "list", "export"],
    })
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"
    assert h.status == "running"

    r = h.submit({
        "test_file": "tests/test_vault.py",
        "test_count": 18,
        "test_cases": [
            "test_init_creates_vault_file",
            "test_add_entry_stores_encrypted",
            "test_get_entry_decrypts_to_clipboard",
            "test_list_shows_all_entry_names",
            "test_export_json_format_matches_readme",
            "test_wrong_master_password_fails",
        ],
    })
    assert r
    assert r.new_step == "2.3 Run tests"
    assert h.step == "2.3 Run tests"
    assert h.status == "running"

    r = h.submit({
        "command": "pytest tests/ -v --cov=vaultctl",
        "passed": 18, "failed": 0, "coverage": "94%",
    })
    assert r
    assert h.step == "3.1 Align code with README"
    assert h.status == "running"

    # Phase 3: Alignment passes -- all CLI commands match README examples
    r = h.submit_goto("3.2 Final review")
    assert r
    assert r.new_step == "3.2 Final review"
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    # Final review passes (WAIT+LLM: approve first, then submit_goto)
    r = h.approve()
    assert r
    assert h.step == "3.2 Final review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Verify done state
    r = h.submit({})
    assert not r
    assert "completed" in r.message.lower() or "Workflow is already completed" in r.message


def test_scenario_2_readme_review_rejected(harness_factory):
    """Markdown-to-PDF library: README rejected twice for unclear API, approved with full examples."""
    h = harness_factory("p1-rdd.yaml")
    r = h.start()
    assert r

    assert h.step == "1.1 Write README draft"
    assert h.status == "running"

    # V1: just a one-liner description
    r = h.submit({
        "readme": "# md2pdf\nConvert Markdown to PDF.",
        "version": "v1",
        "issue": "Too brief, no API examples, no installation instructions",
    })
    assert r
    assert r.new_step == "1.2 README review"
    assert h.step == "1.2 README review"
    assert h.status == "waiting"

    # First rejection: no usage examples
    r = h.approve()
    assert r
    assert h.step == "1.2 README review"
    assert h.status == "running"

    r = h.submit_goto("1.1 Write README draft")
    assert r
    assert r.new_step == "1.1 Write README draft"
    assert h.step == "1.1 Write README draft"
    assert h.status == "running"

    # V2: added usage but missing error handling and config docs
    r = h.submit({
        "readme": (
            "# md2pdf\n\n## Install\n```pip install md2pdf```\n\n"
            "## Usage\n```python\nfrom md2pdf import convert\nconvert('input.md', 'output.pdf')\n```"
        ),
        "version": "v2",
        "issue": "Missing configuration options, custom CSS support, error handling docs",
    })
    assert r
    assert r.new_step == "1.2 README review"
    assert h.step == "1.2 README review"
    assert h.status == "waiting"

    # Second rejection: still missing config and error handling
    r = h.approve()
    assert r
    assert h.step == "1.2 README review"
    assert h.status == "running"

    r = h.submit_goto("1.1 Write README draft")
    assert r
    assert r.new_step == "1.1 Write README draft"
    assert h.step == "1.1 Write README draft"
    assert h.status == "running"

    # V3: comprehensive with all sections
    r = h.submit({
        "readme": (
            "# md2pdf\n\n"
            "## Install\n```pip install md2pdf```\n\n"
            "## Quick Start\n```python\nfrom md2pdf import convert\nconvert('input.md', 'output.pdf')\n```\n\n"
            "## Configuration\n```python\nconvert('input.md', 'output.pdf', css='custom.css', "
            "margins={'top': '1in'})\n```\n\n"
            "## Error Handling\n```python\ntry:\n    convert(path)\n"
            "except FileNotFoundError:\n    ...\nexcept ConversionError as e:\n    ...\n```"
        ),
        "version": "v3",
    })
    assert r
    assert r.new_step == "1.2 README review"
    assert h.step == "1.2 README review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.step == "1.2 README review"
    assert h.status == "running"

    r = h.submit_goto("2.1 Implement code")
    assert r
    assert r.new_step == "2.1 Implement code"
    assert h.step == "2.1 Implement code"
    assert h.status == "running"


def test_scenario_3_alignment_fails_back_to_implementation(harness_factory):
    """Git hook manager: implementation misses --global flag documented in README, fix and re-align."""
    h = harness_factory("p1-rdd.yaml")
    r = h.start()
    assert r

    # Get through README phase (WAIT+LLM)
    r = h.submit({
        "readme": (
            "# hookr -- Git Hook Manager\n\n"
            "## Usage\n"
            "```bash\nhookr install           # Install hooks for current repo\n"
            "hookr install --global  # Install hooks globally\n"
            "hookr run pre-commit    # Run a specific hook\n```"
        ),
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert h.step == "2.1 Implement code"
    assert h.status == "running"

    # Implement (V1: missing --global flag support)
    r = h.submit({
        "files": ["hookr/cli.py", "hookr/installer.py"],
        "note": "Implemented install and run commands, but forgot --global flag",
    })
    assert r
    r = h.submit({
        "test_file": "tests/test_hookr.py",
        "test_count": 8,
    })
    assert r
    r = h.submit({"passed": 8, "failed": 0, "coverage": "82%"})
    assert r
    assert h.step == "3.1 Align code with README"
    assert h.status == "running"

    # Alignment fails: --global flag documented in README but not implemented
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert r.new_step == "2.1 Implement code"
    assert h.step == "2.1 Implement code"
    assert h.status == "running"

    # Re-implement with --global support
    r = h.submit({
        "files_modified": ["hookr/cli.py", "hookr/installer.py"],
        "fix": "Added --global flag: writes to ~/.config/git/hooks/ instead of .git/hooks/",
    })
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"
    r = h.submit({
        "test_file": "tests/test_hookr.py",
        "added_tests": ["test_install_global_creates_config_hooks_dir"],
    })
    assert r
    assert r.new_step == "2.3 Run tests"
    assert h.step == "2.3 Run tests"
    r = h.submit({"passed": 11, "failed": 0, "coverage": "91%"})
    assert r
    assert h.step == "3.1 Align code with README"

    # This time alignment passes
    r = h.submit_goto("3.2 Final review")
    assert r
    assert r.new_step == "3.2 Final review"
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.step == "3.2 Final review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_scenario_4_repeated_alignment_3_rounds(harness_factory):
    """JSON schema validator: 3 alignment failures (missing features from README) before passing."""
    h = harness_factory("p1-rdd.yaml")
    r = h.start()
    assert r

    # Get through README review (WAIT+LLM)
    r = h.submit({
        "readme": (
            "# jsonval -- JSON Schema Validator\n\n"
            "## Features\n"
            "- Draft 2020-12 support\n"
            "- Custom format validators\n"
            "- Detailed error paths (JSONPointer)\n"
            "- Remote $ref resolution\n"
        ),
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert h.step == "2.1 Implement code"
    assert h.status == "running"

    # Round 1: missing custom format validators
    r = h.submit({
        "files": ["jsonval/validator.py", "jsonval/schema.py"],
        "gap": "Custom format validators not implemented yet",
    })
    assert r
    r = h.submit({"test_file": "tests/test_validator.py", "count": 12})
    assert r
    r = h.submit({"passed": 12, "failed": 0})
    assert r
    assert h.step == "3.1 Align code with README"
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert r.new_step == "2.1 Implement code"
    assert h.step == "2.1 Implement code"

    # Round 2: added format validators, but error paths use array index not JSONPointer
    r = h.submit({
        "files_modified": ["jsonval/formats.py"],
        "gap": "Error paths use array[0] style instead of JSONPointer /items/0",
    })
    assert r
    r = h.submit({"added_tests": ["test_custom_date_format", "test_custom_email_format"]})
    assert r
    r = h.submit({"passed": 16, "failed": 0})
    assert r
    assert h.step == "3.1 Align code with README"
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert r.new_step == "2.1 Implement code"
    assert h.step == "2.1 Implement code"

    # Round 3: fixed JSONPointer but remote $ref not working
    r = h.submit({
        "files_modified": ["jsonval/errors.py"],
        "gap": "Remote $ref resolution returns raw URL instead of dereferenced schema",
    })
    assert r
    r = h.submit({"added_tests": ["test_jsonpointer_error_path"]})
    assert r
    r = h.submit({"passed": 19, "failed": 0})
    assert r
    assert h.step == "3.1 Align code with README"
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert r.new_step == "2.1 Implement code"
    assert h.step == "2.1 Implement code"

    # Round 4: all README features implemented
    r = h.submit({
        "files_modified": ["jsonval/ref_resolver.py"],
        "note": "All 4 README features now fully implemented",
    })
    assert r
    r = h.submit({"added_tests": ["test_remote_ref_resolution"]})
    assert r
    r = h.submit({"passed": 24, "failed": 0, "coverage": "96%"})
    assert r
    assert h.step == "3.1 Align code with README"
    r = h.submit_goto("3.2 Final review")
    assert r
    assert r.new_step == "3.2 Final review"
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.step == "3.2 Final review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_scenario_5_skip_testing(harness_factory):
    """Config file parser: skip writing tests (comprehensive test suite exists from v1)."""
    h = harness_factory("p1-rdd.yaml")
    r = h.start()
    assert r

    # Get through README review (WAIT+LLM)
    r = h.submit({
        "readme": (
            "# confparse -- Multi-format Config Parser\n\n"
            "Supports YAML, TOML, JSON, and INI with a unified API.\n\n"
            "```python\nfrom confparse import load\nconfig = load('app.toml')\n```"
        ),
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert h.step == "2.1 Implement code"
    assert h.status == "running"

    r = h.submit({
        "files": ["confparse/loader.py", "confparse/parsers/toml.py", "confparse/parsers/yaml.py"],
        "note": "V2 refactor -- parsers extracted to plugins, tests from v1 still apply",
    })
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"

    # Skip writing tests -- v1 test suite is comprehensive and still valid
    r = h.skip("Tests already exist from v1 (42 tests in tests/test_confparse.py)")
    assert r
    assert r.new_step == "2.3 Run tests"
    assert h.step == "2.3 Run tests"
    assert h.status == "running"

    # Run existing tests
    r = h.submit({
        "command": "pytest tests/ -v",
        "passed": 42, "failed": 0, "coverage": "88%",
    })
    assert r
    assert h.step == "3.1 Align code with README"
    assert h.status == "running"

    r = h.submit_goto("3.2 Final review")
    assert r
    assert r.new_step == "3.2 Final review"
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.step == "3.2 Final review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_scenario_6_stop_then_resume(harness_factory):
    """HTTP client library: stop mid-test-writing for deploy freeze, resume after."""
    h = harness_factory("p1-rdd.yaml")
    r = h.start()
    assert r

    # Get through README review (WAIT+LLM)
    r = h.submit({
        "readme": (
            "# fetchr -- Typed HTTP Client\n\n"
            "```python\nfrom fetchr import Client\n"
            "client = Client(base_url='https://api.example.com')\n"
            "resp = client.get('/users', params={'page': 1})\n```\n\n"
            "## Features\n- Automatic retry with exponential backoff\n"
            "- Response type coercion via generics\n"
            "- Request/response middleware pipeline\n"
        ),
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert h.step == "2.1 Implement code"
    assert h.status == "running"

    r = h.submit({
        "files": ["fetchr/client.py", "fetchr/middleware.py", "fetchr/retry.py"],
        "summary": "Client with httpx backend, middleware chain, retry decorator",
    })
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"
    assert h.status == "running"

    # Deploy freeze -- stop work until Monday
    r = h.stop()
    assert r
    assert r.message
    assert h.status == "stopped"
    assert h.step == "2.2 Write tests"

    # Monday: resume
    r = h.resume()
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.status == "running"
    assert h.step == "2.2 Write tests"

    # Continue from where we left off
    r = h.submit({
        "test_file": "tests/test_client.py",
        "test_count": 15,
        "notable_tests": [
            "test_retry_on_503_with_backoff",
            "test_middleware_modifies_request_headers",
            "test_generic_response_type_coercion",
        ],
    })
    assert r
    assert r.new_step == "2.3 Run tests"
    assert h.step == "2.3 Run tests"

    r = h.submit({"passed": 15, "failed": 0, "coverage": "87%"})
    assert r
    assert h.step == "3.1 Align code with README"

    r = h.submit_goto("3.2 Final review")
    assert r
    assert r.new_step == "3.2 Final review"
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.step == "3.2 Final review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_scenario_7_complete_then_reset(harness_factory):
    """Env variable loader V1 shipped, reset to build V2 with .env.vault support."""
    h = harness_factory("p1-rdd.yaml")
    r = h.start()
    assert r

    # Quick path to Done (WAIT+LLM steps need approve + submit_goto)
    r = h.submit({
        "readme": "# dotenv-go\nLoad .env files into os.Environ with type coercion.",
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Implement code")
    assert r
    r = h.submit({"files": ["dotenv.go", "parser.go"]})
    assert r
    r = h.submit({"test_file": "dotenv_test.go", "count": 20})
    assert r
    r = h.submit({"passed": 20, "failed": 0})
    assert r
    r = h.submit_goto("3.2 Final review")
    assert r
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Verify completed state
    status = h.get_status()
    assert status["status"] == "done"
    assert status["current_step"] == "Done"

    # Verify done state: further submits rejected
    r = h.submit({})
    assert not r
    assert "completed" in r.message.lower() or "Workflow is already completed" in r.message

    # V1 shipped. Reset to start V2 with encrypted .env.vault support
    h.reset()
    assert h.state is None

    # Start V2 README-first
    r = h.start()
    assert r
    assert h.step == "1.1 Write README draft"
    assert h.status == "running"


def test_scenario_8_goto_test_step(harness_factory):
    """Migration tool: code and tests exist, goto run tests to verify after refactor."""
    h = harness_factory("p1-rdd.yaml")
    r = h.start()
    assert r

    # Get through README review (WAIT+LLM)
    r = h.submit({
        "readme": (
            "# migratron -- Database Migration Runner\n\n"
            "```bash\nmigratron up       # Apply pending migrations\n"
            "migratron down 1   # Rollback last migration\n"
            "migratron status   # Show migration state\n```"
        ),
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert h.step == "2.1 Implement code"
    assert h.status == "running"

    # Jump directly to run tests (code and tests already written, just need to re-run after refactor)
    r = h.goto("2.3 Run tests")
    assert r
    assert r.new_step == "2.3 Run tests"
    assert h.step == "2.3 Run tests"
    assert h.status == "running"

    # Continue from there
    r = h.submit({
        "command": "pytest tests/test_migratron.py -v",
        "passed": 28, "failed": 0,
        "note": "All tests pass after internal refactor from pathlib to os.path",
    })
    assert r
    assert h.step == "3.1 Align code with README"
    assert h.status == "running"

    r = h.submit_goto("3.2 Final review")
    assert r
    assert r.new_step == "3.2 Final review"
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "3.2 Final review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_scenario_9_back(harness_factory):
    """Task queue library: use back() to revise README and re-implement after realizing design flaw."""
    h = harness_factory("p1-rdd.yaml")
    r = h.start()
    assert r

    # Move forward with initial README
    r = h.submit({
        "readme": (
            "# taskq -- In-Process Task Queue\n\n"
            "```python\nfrom taskq import Queue\nq = Queue(workers=4)\n"
            "q.enqueue(my_function, arg1, arg2)\n```"
        ),
    })
    assert r
    assert r.new_step == "1.2 README review"
    assert h.step == "1.2 README review"

    # Realize the README should show async support too -- go back
    r = h.back()
    assert r
    assert r.new_step == "1.1 Write README draft"
    assert h.step == "1.1 Write README draft"
    assert h.status == "running"

    # Go forward with improved README including async
    r = h.submit({
        "readme": (
            "# taskq -- In-Process Task Queue\n\n"
            "## Sync\n```python\nq = Queue(workers=4)\nq.enqueue(fn, arg)\n```\n\n"
            "## Async\n```python\nq = AsyncQueue(workers=4)\nawait q.enqueue(async_fn, arg)\n```"
        ),
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert h.step == "2.1 Implement code"
    assert h.status == "running"

    r = h.submit({
        "files": ["taskq/queue.py", "taskq/async_queue.py", "taskq/worker.py"],
    })
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"

    # Realize worker pool design is wrong -- go back to re-implement
    r = h.back()
    assert r
    assert r.new_step == "2.1 Implement code"
    assert h.step == "2.1 Implement code"
    assert h.status == "running"

    # Re-implement with thread pool executor pattern
    r = h.submit({
        "files_modified": ["taskq/worker.py"],
        "fix": "Switched from manual threading to concurrent.futures.ThreadPoolExecutor",
    })
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"
    r = h.submit({
        "test_file": "tests/test_taskq.py",
        "test_count": 14,
    })
    assert r
    assert r.new_step == "2.3 Run tests"
    assert h.step == "2.3 Run tests"
    r = h.submit({"passed": 14, "failed": 0})
    assert r
    assert h.step == "3.1 Align code with README"

    r = h.submit_goto("3.2 Final review")
    assert r
    assert r.new_step == "3.2 Final review"
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_scenario_10_modify_yaml_add_api_doc_step(harness_factory):
    """REST API SDK: mid-sprint add OpenAPI spec generation step to the workflow."""
    h = harness_factory("p1-rdd.yaml")
    r = h.start()
    assert r

    # Work partway through (WAIT+LLM for 1.2)
    r = h.submit({
        "readme": (
            "# stripe-lite -- Lightweight Stripe SDK\n\n"
            "```python\nfrom stripe_lite import Stripe\n"
            "s = Stripe(api_key='sk_test_...')\n"
            "charge = s.charges.create(amount=2000, currency='usd')\n```"
        ),
    })
    assert r
    r = h.approve()
    assert r
    r = h.submit_goto("2.1 Implement code")
    assert r
    r = h.submit({
        "files": ["stripe_lite/client.py", "stripe_lite/resources/charges.py"],
    })
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"

    # Team decides: need OpenAPI spec generation before implementation
    modified_yaml = """名称: RDD Development
描述: README-Driven Development with API docs

步骤:
  - 1.1 Write README draft

  - 1.2 README review:
      类型: wait
      下一步:
        - 如果: "README is approved"
          去: 1.3 Write API docs
        - 去: 1.1 Write README draft

  - 1.3 Write API docs

  - 2.1 Implement code

  - 2.2 Write tests

  - 2.3 Run tests

  - 3.1 Align code with README:
      下一步:
        - 如果: "code fully aligns with README"
          去: 3.2 Final review
        - 如果: "code needs minor fixes"
          去: 2.1 Implement code
        - 去: 1.1 Write README draft

  - 3.2 Final review:
      类型: wait
      下一步:
        - 如果: "everything is aligned and approved"
          去: Done
        - 去: 2.1 Implement code

  - Done:
      类型: terminate
      原因: README and implementation aligned
"""
    h.reload_yaml(modified_yaml)

    # Jump to the new API doc step to generate OpenAPI spec
    r = h.goto("1.3 Write API docs")
    assert r
    assert r.new_step == "1.3 Write API docs"
    assert h.step == "1.3 Write API docs"
    assert h.status == "running"

    # Submit OpenAPI spec, should advance to implementation
    r = h.submit({
        "api_docs": "openapi/stripe-lite.yaml",
        "spec_version": "3.1.0",
        "endpoints": ["/v1/charges", "/v1/customers", "/v1/refunds"],
    })
    assert r
    assert r.new_step == "2.1 Implement code"
    assert h.step == "2.1 Implement code"
    assert h.status == "running"

    # Continue the rest of the flow
    r = h.submit({
        "files": ["stripe_lite/client.py", "stripe_lite/resources/charges.py"],
        "note": "Re-implemented to match OpenAPI spec",
    })
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"
    r = h.submit({"test_file": "tests/test_charges.py", "count": 9})
    assert r
    assert r.new_step == "2.3 Run tests"
    assert h.step == "2.3 Run tests"
    r = h.submit({"passed": 9, "failed": 0})
    assert r
    assert h.step == "3.1 Align code with README"

    r = h.submit_goto("3.2 Final review")
    assert r
    assert r.new_step == "3.2 Final review"
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.step == "3.2 Final review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Data accumulation tests
# ===============================================================

def test_data_accumulates_readme(harness_factory):
    """Submit data at 1.1 persists in state.data."""
    h = harness_factory("p1-rdd.yaml")
    h.start()

    h.submit({"readme": "# My Project"})
    data = h.state.data
    assert "1.1 Write README draft" in data
    assert data["1.1 Write README draft"]["readme"] == "# My Project"


def test_data_accumulates_implementation(harness_factory):
    """Data submitted during implementation phase persists."""
    h = harness_factory("p1-rdd.yaml")
    _enter_implementation(h)

    h.submit({"code": "main.py", "lines": 150})
    data = h.state.data
    assert "2.1 Implement code" in data
    assert data["2.1 Implement code"]["code"] == "main.py"

    h.submit({"tests": "test_main.py", "count": 10})
    data = h.state.data
    assert "2.2 Write tests" in data
    assert data["2.2 Write tests"]["tests"] == "test_main.py"


def test_data_accumulates_all_phases(harness_factory):
    """Data accumulates across all workflow phases."""
    h = harness_factory("p1-rdd.yaml")
    h.start()

    h.submit({"readme": "v1"})
    h.approve()
    h.submit_goto("2.1 Implement code")
    h.submit({"code": "impl"})
    h.submit({"tests": "test"})
    h.submit({"result": "pass"})

    data = h.state.data
    assert "1.1 Write README draft" in data
    assert "2.1 Implement code" in data
    assert "2.2 Write tests" in data
    assert "2.3 Run tests" in data


# ===============================================================
# History audit trail tests
# ===============================================================

def test_history_audit_full_walkthrough(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.submit({})
    h.approve()
    h.submit_goto("2.1 Implement code")
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("3.2 Final review")
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "approve" in actions
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_history_records_goto(harness_factory):
    """History records goto action."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.goto("2.1 Implement code")

    history = h.get_history(10)
    actions = [e["action"] for e in history]
    assert "goto" in actions


def test_history_records_skip(harness_factory):
    """Skip reason appears in history."""
    h = harness_factory("p1-rdd.yaml")
    _enter_implementation(h)
    h.submit({})
    assert h.step == "2.2 Write tests"

    h.skip("tests exist")
    history = h.get_history(10)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "tests exist"


def test_history_records_reject(harness_factory):
    """Reject action appears in history."""
    h = harness_factory("p1-rdd.yaml")
    _walk_to_readme_review(h)

    h.reject("too brief")
    history = h.get_history(10)
    reject_entries = [e for e in history if e["action"] == "reject"]
    assert len(reject_entries) >= 1
    assert reject_entries[0]["data"] == "too brief"


# ===============================================================
# Cross-executor recovery tests
# ===============================================================

def test_cross_executor_at_readme_review(harness_factory):
    """Close executor at README review, reopen, continue."""
    h = harness_factory("p1-rdd.yaml")
    _walk_to_readme_review(h)

    h.new_executor()

    assert h.step == "1.2 README review"
    assert h.status == "waiting"

    h.approve()
    r = h.submit_goto("2.1 Implement code")
    assert r
    assert h.step == "2.1 Implement code"


def test_cross_executor_at_implementation(harness_factory):
    """Close executor during implementation, reopen, state preserved."""
    h = harness_factory("p1-rdd.yaml")
    _enter_implementation(h)
    h.submit({"code": "main.py"})
    assert h.step == "2.2 Write tests"

    h.new_executor()

    assert h.step == "2.2 Write tests"
    assert h.status == "running"


def test_cross_executor_at_alignment(harness_factory):
    """Close executor at alignment check, reopen, continue."""
    h = harness_factory("p1-rdd.yaml")
    _walk_to_alignment(h)

    h.new_executor()

    assert h.step == "3.1 Align code with README"
    assert h.status == "running"

    r = h.submit_goto("3.2 Final review")
    assert r
    assert h.step == "3.2 Final review"


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.goto("3.2 Final review")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p1-rdd.yaml")
    _enter_implementation(h)

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "2.1 Implement code"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"


# ===============================================================
# Node validation tests
# ===============================================================

def test_node_validates_readme(harness_factory):
    """Validate node rejects bad data at 1.1, accepts good data."""
    h = harness_factory("p1-rdd.yaml")
    h.start()

    h.register_node(
        "1.1 Write README draft",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("readme") else "must include readme content",
        ),
    )

    r = h.submit({"notes": "no readme"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"readme": "# Project README"})
    assert r
    assert r.new_step == "1.2 README review"


def test_node_validates_code(harness_factory):
    """Validate node rejects missing code at 2.1."""
    h = harness_factory("p1-rdd.yaml")
    _enter_implementation(h)

    h.register_node(
        "2.1 Implement code",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("code") else "must include code",
        ),
    )

    r = h.submit({"notes": "no code"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"code": "main.py"})
    assert r
    assert r.new_step == "2.2 Write tests"


def test_node_validates_tests(harness_factory):
    """Validate node rejects missing tests at 2.2."""
    h = harness_factory("p1-rdd.yaml")
    _enter_implementation(h)
    h.submit({"code": "main.py"})
    assert h.step == "2.2 Write tests"

    h.register_node(
        "2.2 Write tests",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("tests") else "must include tests",
        ),
    )

    r = h.submit({})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"tests": "test_main.py"})
    assert r
    assert r.new_step == "2.3 Run tests"


# ===============================================================
# Node archival tests
# ===============================================================

def test_node_archives_readme(harness_factory):
    """Archive node writes readme data to SQLite."""
    h = harness_factory("p1-rdd.yaml")
    h.start()

    h.register_node(
        "1.1 Write README draft",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"readme_content": "string", "version": "string"}},
            archive={"table": "readme_drafts"},
        ),
    )

    r = h.submit({"readme_content": "# My Project", "version": "v1"})
    assert r

    rows = h.get_archived_rows("readme_drafts")
    assert len(rows) == 1
    assert rows[0]["readme_content"] == "# My Project"
    assert rows[0]["version"] == "v1"


def test_node_archives_code(harness_factory):
    """Archive node writes implementation data to SQLite."""
    h = harness_factory("p1-rdd.yaml")
    _enter_implementation(h)

    h.register_node(
        "2.1 Implement code",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"module": "string"}},
            archive={"table": "code_modules"},
        ),
    )

    r = h.submit({"module": "auth.py"})
    assert r

    rows = h.get_archived_rows("code_modules")
    assert len(rows) == 1
    assert rows[0]["module"] == "auth.py"


def test_node_archives_multiple_alignment_rounds(harness_factory):
    """Archive node at 2.1 accumulates rows across alignment retry rounds."""
    h = harness_factory("p1-rdd.yaml")
    _enter_implementation(h)

    h.register_node(
        "2.1 Implement code",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"attempt": "string"}},
            archive={"table": "impl_attempts"},
        ),
    )

    # Round 1
    h.submit({"attempt": "round1"})
    h.submit({})
    h.submit({})
    h.submit_goto("2.1 Implement code")

    # Round 2
    h.submit({"attempt": "round2"})

    rows = h.get_archived_rows("impl_attempts")
    assert len(rows) == 2


# ===============================================================
# Error boundary tests
# ===============================================================

def test_submit_on_waiting_fails(harness_factory):
    """Submit while waiting returns failure."""
    h = harness_factory("p1-rdd.yaml")
    _walk_to_readme_review(h)

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.goto("3.2 Final review")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.goto("3.2 Final review")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.submit({"readme": "# Draft"})
    assert h.step == "1.2 README review"

    h.save_checkpoint("at_review")

    h.approve()
    h.submit_goto("2.1 Implement code")
    assert h.step == "2.1 Implement code"

    restored = h.load_checkpoint("at_review")
    assert restored is not None
    assert restored.current_step == "1.2 README review"
    assert "1.1 Write README draft" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    assert h.step == "1.1 Write README draft"

    r = h.retry()
    assert r
    assert h.step == "1.1 Write README draft"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p1-rdd.yaml")
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p1-rdd.yaml")
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p1-rdd.yaml")

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Write README draft"


def test_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_reset_clears_data(harness_factory):
    """After reset, state is None."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.submit({"readme": "content"})

    h.reset()
    assert h.state is None


def test_reject_preserves_data(harness_factory):
    """Reject does not modify state.data."""
    h = harness_factory("p1-rdd.yaml")
    _walk_to_readme_review(h)

    data_before = dict(h.state.data)
    h.reject("nope")
    data_after = h.state.data
    assert data_before == data_after


def test_history_records_transition(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p1-rdd.yaml")
    h.start()
    h.submit({})

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


# ═══════════════════════════════════════════════════════
# Turing machine condition checker tests
# ═══════════════════════════════════════════════════════

def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p1-rdd.yaml")
    h.start()

    h.register_node(
        "1.1 Write README draft",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nWrite README draft.\n\n## Steps\n1. Analyze\n2. Write",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory("p1-rdd.yaml")
    h.start()

    h.register_node(
        "1.1 Write README draft",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["edit_policy"] is not None
    assert status["node"]["edit_policy"]["default"] == "block"
