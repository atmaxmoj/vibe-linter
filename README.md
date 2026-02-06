# vibe-linter

A co-agentic workflow engine for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

vibe-linter is a deterministic state machine that pairs with Claude Code to form a dual-agent system. One side handles structure: workflow graphs, state transitions, edit constraints. The other side handles cognition: understanding requirements, writing code, making judgments. Neither can complete a development workflow alone. Together they can.

## The Duality

Every transition in a vibe-linter workflow carries a condition. The engine classifies each condition into exactly one of three types:

```python
def _classify_condition(condition: str) -> str:
    if condition.startswith("@"):       return "eval_node"    # user-defined function
    if has_operators(condition):         return "expression"   # tests_pass == true
    return "llm"                                              # "design is approved"
```

This creates a partition of the condition space:

```
C = C_deterministic ⊔ C_cognitive

C_deterministic = { c ∈ C : classify(c) ∈ {expression, eval_node} }
C_cognitive     = { c ∈ C : classify(c) = llm }
```

Both subsets map through the same interface `Condition → Target`, but with different evaluation mechanisms:

- **C_deterministic**: the engine evaluates autonomously (expression evaluation, Python function calls)
- **C_cognitive**: Claude evaluates by understanding context, then submits `{"_goto": "target"}`

Each side is the complement of the other. This is a duality in the mathematical sense: two complementary faces of the same formal structure. The shared morphism `eval: C → Target` factors through two disjoint paths. Remove either side and `eval` becomes a partial function. The system is irreducible.

```
┌──────────────────────────────┐       ┌──────────────────────────────┐
│        vibe-linter            │       │        Claude Code            │
│                               │       │                              │
│  Workflow graph (structure)   │       │  Code generation (cognition) │
│  State transitions            │◄─────►│  Judgment calls              │
│  Edit policy enforcement      │       │  Requirement understanding   │
│  Loop / branch control        │       │  Design decisions            │
│  Data persistence             │       │  Test evaluation             │
│                               │       │                              │
│  Evaluates: C_deterministic   │       │  Evaluates: C_cognitive      │
└──────────────────────────────┘       └──────────────────────────────┘
```

## Quick Start

```bash
pip install vibe-linter
cd your-project

# Initialize with a workflow template
vibe init tdd

# Configure Claude Code integration (hooks + MCP server)
vibe setup

# Compile and validate the workflow
vibe load tdd

# Start the workflow — Claude Code takes over
vibe start
```

After `vibe start`, Claude Code operates within the workflow. It reads instructions from `vibe_get_status()`, executes each step, and submits results via `vibe_submit_output()`. The engine validates, persists, and routes to the next step. If a transition requires judgment (LLM-classified), Claude decides. If it's deterministic, the engine decides automatically.

## Workflow Definition

Workflows are YAML files in `.vibe/flows/`. They define a directed graph of steps with conditional transitions:

```yaml
name: TDD Development
description: Test-Driven Development — Red, Green, Refactor

steps:
  - 0.1 Collect scenario:
      next:
        - if: "has bug description or feature request"
          go: 1.1 Gather requirements
        - go: 0.1 Collect scenario

  - 1.1 Gather requirements:
      next:
        - if: "this is a hotfix with known root cause"
          go: 2.1 Write failing test (Red)
        - go: 1.2 Design architecture

  - 1.2 Design architecture

  - 1.3 Design review:
      next:
        - if: "design is approved"
          go: 2.0 Feature loop
        - go: 1.2 Design architecture

  - 2.0 Feature loop:
      iterate: "features"
      children:
        - 2.1 Write failing test (Red)
        - 2.2 Write minimal code (Green)
        - 2.3 Refactor
        - 2.4 Run test suite
        - 2.5 Quality check:
            next:
              - if: "all tests pass and code quality is good"
                go: 2.0 Feature loop
              - if: "tests fail due to code bugs"
                go: 2.2 Write minimal code (Green)
              - if: "tests themselves are wrong"
                go: 2.1 Write failing test (Red)
              - if: "design flaw discovered"
                go: 1.2 Design architecture

  - 3.1 Integration testing

  - 3.2 Final review:
      next:
        - if: "all integration tests pass"
          go: Done
        - go: 2.0 Feature loop

  - Done:
      type: terminate
      reason: All features implemented and tests pass
```

The parser also accepts Chinese keywords (`steps`/`步骤`, `if`/`如果`, `go`/`去`, etc.) and normalizes them to English internally.

## Built-in Templates

| Template | Steps | Description |
|----------|-------|-------------|
| `tdd` | 12 | Red-Green-Refactor with design review and feature loop |
| `bugfix` | 5 | Reproduce, fix, verify with retry loops |
| `feature` | 8 | Requirements, design, implement, test, review |

```bash
vibe init tdd      # or bugfix, feature
```

## How It Works

### Claude Code Integration

`vibe setup` configures three integration points in `.claude/settings.json`:

**MCP Server** — 13 `vibe_*` tools Claude Code calls to interact with the engine:

| Tool | Purpose |
|------|---------|
| `vibe_get_status()` | Current step, instructions, pending decisions |
| `vibe_get_context(key)` | Read workflow data |
| `vibe_submit_output(data)` | Submit work, trigger transition |
| `vibe_goto(target)` | Jump to a specific step |
| `vibe_approve()` / `vibe_reject()` | Approval gates |
| `vibe_skip_current()` / `vibe_retry_current()` | Step control |
| `vibe_stop()` / `vibe_resume()` | Pause / resume |
| `vibe_get_history()` / `vibe_back()` | Navigation |

**PreToolUse Hook** — intercepts Write/Edit tool calls. Checks whether a scenario has been collected and whether the current step's edit policy allows the file. Blocks or warns accordingly.

**SessionStart Hook** — injects workflow context when Claude Code starts a session.

### Execution Loop

```
Claude Code session starts
    │
    ▼
SessionStart hook injects context
    │
    ▼
Claude calls vibe_get_status()
    │
    ▼
Engine returns: current step, instructions, pending decisions
    │
    ▼
Claude executes the step
    │
    ▼
Claude calls vibe_submit_output({...})
    │
    ├─ Engine validates output against node schema
    ├─ Engine stores data in SQLite
    ├─ Engine evaluates transitions:
    │     Pass 1: deterministic conditions (expression, @eval_node)
    │     Pass 2: LLM conditions → present to Claude with _goto hint
    │     Pass 3: default transition (unconditional)
    │
    ▼
Next step becomes current → repeat
```

### Edit Policy

Each workflow step can constrain which files Claude is allowed to modify:

```python
# .vibe/nodes/gather_requirements.py
from vibe_linter import node

@node("validate")
def gather_requirements():
    return {
        "instructions": "Understand what needs to be built",
        "edit_policy": {
            "default": "block",
            "patterns": [
                {"glob": "*.md", "policy": "silent"},
                {"glob": "docs/**", "policy": "silent"},
            ]
        },
        "schema": {
            "output": {"requirements": "string", "scope": "string"}
        },
        "check": lambda output: (
            "requirements cannot be empty" if not output.get("requirements") else True
        ),
    }
```

Policy levels: `silent` (allow), `warn` (allow with warning), `block` (prevent edit).

### State Persistence

Workflow state lives in `.vibe/state.db` (SQLite):

- **workflow_state** — current step, status, accumulated data, loop counters
- **workflow_history** — full audit trail of every action
- **workflow_checkpoints** — named snapshots for rollback

State survives across Claude Code sessions. Stop, close your terminal, come back later, and the workflow resumes exactly where it left off.

## CLI Reference

```
vibe init [template]   Initialize project with a workflow template
vibe setup             Configure Claude Code hooks and MCP server
vibe load <flow>       Compile, validate, generate Mermaid diagram
vibe start             Start or resume the loaded workflow
vibe stop              Stop workflow, remove constraints
vibe status            Print current workflow state
vibe reset             Clear state, start fresh
```

## Architecture

```
vibe_linter/
├── cli.py                          CLI router
├── types.py                        FlowDefinition, WorkflowState, EditPolicy, NodeDefinition
├── compiler/
│   ├── parser.py                   YAML → FlowDefinition IR (bilingual keyword support)
│   ├── validator.py                Static analysis: reachability, dead-ends, target resolution
│   └── mermaid.py                  FlowDefinition → Mermaid diagram
├── engine/
│   ├── executor.py                 State machine, condition classification, transition logic
│   ├── expression.py               Template evaluator for {{expr}} and boolean conditions
│   ├── node_loader.py              Dynamic node loading from .vibe/nodes/*.py
│   └── policy.py                   Glob-based edit policy matching
├── store/
│   └── state.py                    SQLite persistence layer
├── integrations/
│   ├── mcp_server.py               MCP server exposing 13 vibe_* tools
│   ├── check_edit.py               PreToolUse hook — edit policy enforcement
│   ├── inject_context.py           SessionStart hook — context injection
│   └── settings.py                 .claude/settings.json configurator
├── commands/
│   ├── init.py, setup.py           Project initialization and Claude Code setup
│   ├── load.py, start.py           Workflow compilation and execution
│   └── stop.py, reset.py           Workflow control
└── templates/
    ├── tdd.yaml                    TDD workflow template
    ├── bugfix.yaml                 Bugfix workflow template
    └── feature.yaml                Feature development template
```

## Why Co-Agentic

The condition classification function partitions every transition into two complementary sets. One set is evaluated by computation. The other is evaluated by cognition. Same interface, same type signature (`Condition → Target`), fundamentally different mechanisms. Each set is exactly what the other is not.

This is not a metaphor. It is a partition `C = C_det ⊔ C_cog` with a shared morphism `eval: C → Target` that factors through two disjoint evaluation paths. The system is irreducible: remove either side and `eval` becomes a partial function. The engine cannot evaluate `"design is approved"`. Claude cannot manage loop iteration state.

Co-agentic means two complementary agents jointly inhabiting one formal structure, each covering exactly the other's gap. The duality is the proof.

## License

MIT
