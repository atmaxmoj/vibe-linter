"""Node definitions for TDD workflow (p1-tdd-auto.yaml).

Each node provides instructions for Claude to execute autonomously.
User is a supervisor — no wait steps, Claude drives the whole flow.
"""
from vibe_linter.engine.node_loader import node


@node("auto")
def collect_scenario():
    return {
        "instructions": """
## Goal
Get a clear scenario from the user before starting any work.

## Check state.data
Look for any of these keys:
- bug_description
- feature_request
- user_story
- requirements

## If found
Submit and proceed:
```
vibe_submit_output({"scenario_collected": true, "type": "bug" | "feature"})
```

## If NOT found
Ask the user what they want to build or fix:
- "What would you like me to work on?"
- "Please describe the bug or feature"

Then wait for their response. Do NOT submit until you have a clear scenario.
""",
        "check": lambda data: (
            True if data.get("scenario_collected")
            else "need scenario from user before proceeding"
        ),
        # Block ALL file edits during scenario collection
        "edit_policy": {
            "default": "block",
            "patterns": [],
        },
    }


@node("auto")
def gather_requirements():
    return {
        "instructions": """
## Goal
Understand what needs to be built/fixed and decide if we can skip to coding.

## Check state.data
Read the scenario (bug_description, feature_request, etc.)

## For HOTFIX (bug with known root cause)
If the scenario clearly describes:
- What's broken
- Where the bug likely is
- User wants it fixed ASAP

Then skip requirements gathering:
```
vibe_submit_output({
    "decision": "hotfix",
    "root_cause_hypothesis": "...",
    "_goto": "2.1 Write failing test (Red)"
})
```

## For NEW FEATURE or UNCLEAR BUG
Gather requirements:
1. Clarify acceptance criteria with user if needed
2. List the specific behaviors to implement/fix
3. Identify affected components (grep for relevant code)

Submit:
```
vibe_submit_output({
    "requirements": ["req1", "req2", ...],
    "acceptance_criteria": ["AC1", "AC2", ...],
    "affected_files": ["path/to/file.py", ...]
})
```
""",
        "check": lambda data: (
            True if data.get("decision") == "hotfix" or data.get("requirements")
            else "must have requirements or hotfix decision"
        ),
        # Block file edits during requirements gathering
        "edit_policy": {
            "default": "block",
            "patterns": [],
        },
    }


@node("auto")
def design_architecture():
    return {
        "instructions": """
## Goal
Design how to implement the requirements.

## Read context
- state.data["1.1 Gather requirements"] has the requirements
- Grep/Read relevant existing code to understand current architecture

## Design
1. Identify components to create/modify
2. Define interfaces between components
3. Choose patterns (if non-trivial)
4. List files to create/modify

## Submit
```
vibe_submit_output({
    "approach": "Brief description of the approach",
    "components": [
        {"name": "ComponentName", "responsibility": "What it does"},
        ...
    ],
    "files_to_modify": ["path/to/file.py", ...],
    "files_to_create": ["path/to/new_file.py", ...],
    "risks": ["Potential issue 1", ...] or []
})
```
""",
        "check": lambda data: (
            True if data.get("approach") and data.get("components")
            else "must have approach and components"
        ),
        # Block file edits during design phase
        "edit_policy": {
            "default": "block",
            "patterns": [],
        },
    }


@node("auto")
def design_review():
    return {
        "instructions": """
## Goal
Self-review the design before implementing.

## Read context
- state.data["1.2 Design architecture"] has the design

## Review checklist
1. Does it solve all requirements?
2. Is it the simplest approach that works?
3. Are there obvious edge cases not handled?
4. Is it consistent with existing codebase patterns?

## If design is GOOD
```
vibe_submit_output({
    "review_result": "approved",
    "notes": "Optional notes",
    "_goto": "2.0 Feature loop"
})
```

## If design needs CHANGES
```
vibe_submit_output({
    "review_result": "needs_revision",
    "issues": ["Issue 1", "Issue 2", ...],
    "_goto": "1.2 Design architecture"
})
```
""",
        "check": lambda data: (
            True if data.get("review_result") in ("approved", "needs_revision")
            else "must have review_result: approved or needs_revision"
        ),
        # Block file edits during design review
        "edit_policy": {
            "default": "block",
            "patterns": [],
        },
    }


@node("auto")
def write_failing_test():
    return {
        "instructions": """
## Goal
Write a test that reproduces the bug or specifies the feature behavior.
The test MUST FAIL — that's the "Red" in Red-Green-Refactor.

## Prerequisite check
If state.data has no scenario (bug_description, feature_request, requirements):
```
vibe_submit_output({"_goto": "0.1 Collect scenario"})
```
Do NOT proceed without a scenario.

## Steps
1. Analyze the scenario to determine:
   - Input: what data/action triggers the behavior
   - Expected: what SHOULD happen
   - Actual (for bugs): what currently happens wrong

2. Find existing test patterns:
   - Grep for similar tests
   - Read test utilities/fixtures

3. Write the test:
   - File: tests/test_<feature>.py or tests/integration/test_<feature>.py
   - Name: test_<behavior>_<condition>
   - Structure: Arrange → Act → Assert
   - Make assertions specific and descriptive

4. Run the test:
   ```bash
   pytest path/to/test_file.py::test_name -v
   ```

5. Verify it FAILS (if it passes, the bug doesn't exist or test is wrong)

## Submit
```
vibe_submit_output({
    "test_file": "tests/test_example.py",
    "test_name": "test_login_case_insensitive_email",
    "test_code": "def test_login_case_insensitive_email():\\n    ...",
    "run_result": "FAILED - AssertionError: ...",
    "failure_analysis": "Why it fails — what's the root cause"
})
```
""",
        "check": lambda data: (
            "missing test_file" if not data.get("test_file") else
            "missing test_code" if not data.get("test_code") else
            "missing run_result" if not data.get("run_result") else
            "test should FAIL at Red phase" if "pass" in data.get("run_result", "").lower()
                and "fail" not in data.get("run_result", "").lower()
            else True
        ),
        "schema": {
            "output": {
                "test_file": "string",
                "test_name": "string",
                "test_code": "string",
                "run_result": "string",
                "failure_analysis": "string",
            }
        },
        # Allow edits - this is an implementation step
        "edit_policy": {
            "default": "silent",
            "patterns": [],
        },
    }


@node("auto")
def write_minimal_code():
    return {
        "instructions": """
## Goal
Write the MINIMAL code to make the failing test pass.
Don't over-engineer. Don't add features. Just make it green.

## Read context
- state.data["2.1 Write failing test (Red)"] has:
  - test_file, test_code: the test to pass
  - failure_analysis: why it fails

## Steps
1. Identify where to make changes (from failure_analysis)

2. Write the smallest change that makes the test pass:
   - If test expects a function, write that function
   - If test expects different behavior, fix that specific behavior
   - Do NOT refactor, do NOT add error handling, do NOT optimize

3. Run the test:
   ```bash
   pytest path/to/test_file.py::test_name -v
   ```

4. If still failing, analyze and fix until green

## Submit
```
vibe_submit_output({
    "files_changed": ["src/services/auth.py"],
    "changes_summary": "Added email.lower() in login() before DB lookup",
    "diff": "- user = User.query.filter_by(email=email)\\n+ user = User.query.filter_by(email=email.lower())",
    "run_result": "PASSED - 1 passed in 0.2s"
})
```
""",
        "check": lambda data: (
            "missing files_changed" if not data.get("files_changed") else
            "missing run_result" if not data.get("run_result") else
            "test should PASS at Green phase" if "fail" in data.get("run_result", "").lower()
                and "pass" not in data.get("run_result", "").lower()
            else True
        ),
        "schema": {
            "output": {
                "files_changed": "string[]",
                "changes_summary": "string",
                "diff": "string",
                "run_result": "string",
            }
        },
        # Allow edits - this is an implementation step
        "edit_policy": {
            "default": "silent",
            "patterns": [],
        },
    }


@node("auto")
def refactor():
    return {
        "instructions": """
## Goal
Improve code quality WITHOUT changing behavior.
Tests must stay green.

## What to look for
1. Duplication — extract common code
2. Naming — make it clearer
3. Structure — split large functions
4. Related code that needs same fix (e.g., if login needs email.lower(), does register too?)

## What NOT to do
- Add new features
- Change behavior
- "Improve" things that aren't related to current work

## Steps
1. Review the changes made in 2.2
2. Identify refactoring opportunities
3. Make changes
4. Run tests to verify still green:
   ```bash
   pytest path/to/test_file.py -v
   ```

## If no refactoring needed
```
vibe_submit_output({
    "refactoring": "none needed",
    "reason": "Code is already clean, single responsibility",
    "run_result": "PASSED - N passed"
})
```

## If refactoring done
```
vibe_submit_output({
    "refactoring": "done",
    "changes": [
        "Extracted normalize_email() helper",
        "Applied same fix to register()"
    ],
    "files_changed": ["src/services/auth.py", "src/utils/email.py"],
    "run_result": "PASSED - N passed"
})
```
""",
        "check": lambda data: (
            "missing refactoring decision" if not data.get("refactoring") else
            "missing run_result" if not data.get("run_result") else
            "tests must pass after refactor" if "fail" in data.get("run_result", "").lower()
                and "pass" not in data.get("run_result", "").lower()
            else True
        ),
        # Allow edits - this is an implementation step
        "edit_policy": {
            "default": "silent",
            "patterns": [],
        },
    }


@node("auto")
def run_test_suite():
    return {
        "instructions": """
## Goal
Run the FULL test suite to catch regressions.

## Steps
1. Run all tests:
   ```bash
   pytest tests/ --tb=short -q
   ```

2. If any failures, note them for quality check

## Submit
```
vibe_submit_output({
    "command": "pytest tests/ --tb=short -q",
    "passed": 47,
    "failed": 0,
    "skipped": 2,
    "run_result": "47 passed, 2 skipped in 3.2s",
    "failures": []  # or ["test_foo: AssertionError...", ...]
})
```
""",
        "check": lambda data: (
            "missing run_result" if not data.get("run_result") else
            True
        ),
        "schema": {
            "output": {
                "command": "string",
                "passed": "number",
                "failed": "number",
                "run_result": "string",
                "failures": "string[]",
            }
        },
        # Warn on edits - this step is for running tests, not editing
        "edit_policy": {
            "default": "warn",
            "patterns": [],
        },
    }


@node("auto")
def quality_check():
    return {
        "instructions": """
## Goal
Decide what to do next based on test results and code quality.

## Read context
- state.data["2.4 Run test suite"] has test results

## Decision tree

### All tests pass + code is clean
→ Continue to next feature (or finish if loop done)
```
vibe_submit_output({
    "decision": "quality_ok",
    "notes": "All 47 tests pass, code is minimal and clean",
    "_goto": "2.0 Feature loop"
})
```

### Tests fail due to CODE BUGS
The implementation is wrong, not the test.
```
vibe_submit_output({
    "decision": "code_bugs",
    "failing_tests": ["test_foo", "test_bar"],
    "analysis": "The fix broke X because Y",
    "_goto": "2.2 Write minimal code (Green)"
})
```

### Tests fail because TESTS ARE WRONG
The test itself has a bug or wrong expectation.
```
vibe_submit_output({
    "decision": "test_bugs",
    "failing_tests": ["test_foo"],
    "analysis": "Test expectation is wrong because...",
    "_goto": "2.1 Write failing test (Red)"
})
```

### DESIGN FLAW discovered
The approach itself is wrong, need to rethink.
```
vibe_submit_output({
    "decision": "design_flaw",
    "issue": "Current approach can't handle X",
    "_goto": "1.2 Design architecture"
})
```
""",
        "check": lambda data: (
            "must have decision" if not data.get("decision") else
            "invalid decision" if data.get("decision") not in
                ("quality_ok", "code_bugs", "test_bugs", "design_flaw")
            else True
        ),
        # Warn on edits - this is a decision step
        "edit_policy": {
            "default": "warn",
            "patterns": [],
        },
    }


@node("auto")
def integration_testing():
    return {
        "instructions": """
## Goal
Run end-to-end / integration tests to verify the full flow works.

## Steps
1. Identify relevant integration tests:
   - Check tests/integration/ or tests/e2e/
   - If none exist for this feature, consider writing one

2. Run integration tests:
   ```bash
   pytest tests/integration/ -v --tb=short
   ```

3. If the feature is user-facing, also do a quick manual sanity check

## Submit
```
vibe_submit_output({
    "integration_tests_run": ["test_login_flow", "test_registration_flow"],
    "passed": 12,
    "failed": 0,
    "run_result": "12 passed in 5.3s",
    "manual_check": "Verified login with mixed-case email works in browser"
})
```
""",
        "check": lambda data: (
            "missing run_result" if not data.get("run_result") else
            True
        ),
        # Allow edits - may need to write integration tests
        "edit_policy": {
            "default": "silent",
            "patterns": [],
        },
    }


@node("auto")
def final_review():
    return {
        "instructions": """
## Goal
Final check before declaring the work done.

## Review checklist
1. All unit tests pass?
2. All integration tests pass?
3. Code is clean (no debug prints, no commented code)?
4. Changes are minimal and focused?

## Read context
- state.data["3.1 Integration testing"] has integration results
- state.data["2.4 Run test suite"] has unit test results

## If everything looks good
```
vibe_submit_output({
    "review_result": "approved",
    "summary": "Fixed email case sensitivity in login/register. 47 unit + 12 integration tests pass.",
    "_goto": "Done"
})
```

## If something needs more work
```
vibe_submit_output({
    "review_result": "needs_work",
    "issues": ["Integration test for X is flaky", ...],
    "_goto": "2.0 Feature loop"
})
```
""",
        "check": lambda data: (
            "must have review_result" if not data.get("review_result") else
            "invalid review_result" if data.get("review_result") not in ("approved", "needs_work")
            else True
        ),
        # Warn on edits - this is a review step
        "edit_policy": {
            "default": "warn",
            "patterns": [],
        },
    }
