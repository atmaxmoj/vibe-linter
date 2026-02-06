"""Test scenarios for Feynman Technique workflow (p7-feynman.yaml).

Tests the Feynman Technique learning workflow including:
- Setup phase (choose topic, list concepts)
- Concept loop with clear/not-clear 2-way branching
- Retry path when explanation is not clear
- Summary phase
- State transitions, gotos, stops/resumes, and hot-reload

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


def _walk_to_concept_loop(h):
    """Start -> choose topic -> list concepts -> enter concept loop."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (loop entry)
    assert h.step == "2.1 Study concept"
    assert h.status == "running"


def _complete_one_concept_clear(h):
    """Complete one concept: study -> explain -> clear -> loop header."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit_goto("2.0 Concept loop")  # clear -> loop header


# ================================================================
# Scenario 1: Happy path 3 concepts
# ================================================================


def test_happy_path_3_concepts(harness_factory):
    """Learning distributed systems: explain CAP theorem, consensus, and eventual consistency."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["cap_theorem", "consensus_algorithms", "eventual_consistency"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Choose topic"
    assert h.status == "running"

    r = h.submit({
        "topic": "Distributed Systems Fundamentals",
        "motivation": "Preparing for system design interviews at FAANG companies",
    })
    assert r
    assert r.new_step == "1.2 List concepts to learn"
    assert h.step == "1.2 List concepts to learn"

    r = h.submit({
        "concepts": [
            "CAP Theorem: consistency, availability, partition tolerance trade-offs",
            "Consensus Algorithms: Paxos, Raft, and leader election",
            "Eventual Consistency: conflict resolution and CRDTs",
        ],
    })
    assert r
    assert r.new_step == "2.1 Study concept"
    assert h.step == "2.1 Study concept"

    study_data = [
        {
            "study": {"concept": "CAP Theorem", "source": "Brewer's 2000 keynote, Gilbert-Lynch proof"},
            "explain": {"explanation": "Imagine 3 friends sharing a notebook. If the notebook gets torn (partition), you must choose: everyone always agrees (consistency) or everyone can always write (availability). You cannot guarantee both when the notebook is split."},
        },
        {
            "study": {"concept": "Consensus Algorithms", "source": "Raft paper by Ongaro and Ousterhout"},
            "explain": {"explanation": "Think of a class electing a note-taker. One student proposes to be the note-taker (leader election). If the majority agrees, that student writes the official notes. If the note-taker is absent, a new election happens. This is basically how Raft works."},
        },
        {
            "study": {"concept": "Eventual Consistency", "source": "Dynamo paper, CRDT survey by Shapiro et al."},
            "explain": {"explanation": "Like a shared Google Doc with offline mode. Two people edit offline and their changes conflict. When they reconnect, the system merges changes automatically using rules (CRDTs). Eventually everyone sees the same document, but not instantly."},
        },
    ]

    for i in range(3):
        assert h.step == "2.1 Study concept"
        r = h.submit(study_data[i]["study"])
        assert r
        assert r.new_step == "2.2 Explain in simple terms"
        assert h.step == "2.2 Explain in simple terms"
        r = h.submit(study_data[i]["explain"])
        assert r
        assert r.new_step == "2.3 Clear enough?"
        assert h.step == "2.3 Clear enough?"

        # Explanation is clear -> next concept / exit loop
        r = h.submit_goto("2.0 Concept loop")
        assert r
        if i < 2:
            assert r.new_step == "2.1 Study concept"
            assert h.step == "2.1 Study concept"

    assert h.step == "3.1 Create summary notes"

    r = h.submit({
        "summary": "Distributed systems: CAP constrains design choices, Raft provides practical consensus, eventual consistency trades immediacy for availability. All three interconnect.",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_happy_path_data_accumulates(harness_factory):
    """Data submitted at each step persists in state.data."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
    h.start()
    h.submit({"topic": "quantum mechanics"})
    assert h.state.data["1.1 Choose topic"]["topic"] == "quantum mechanics"

    h.submit({"concepts_list": "superposition, entanglement"})
    assert h.state.data["1.2 List concepts to learn"]["concepts_list"] == "superposition, entanglement"

    h.submit({"notes": "studied superposition"})
    assert h.state.data["2.1 Study concept"]["notes"] == "studied superposition"


def test_happy_path_history_audit(harness_factory):
    """History contains expected action types for full walkthrough."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Concept loop")
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_happy_path_cross_executor_in_loop(harness_factory):
    """Close executor mid-loop, reopen, state persists."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a", "b", "c"]},
    )
    _walk_to_concept_loop(h)
    h.submit({})
    assert h.step == "2.2 Explain in simple terms"

    h.new_executor()

    assert h.step == "2.2 Explain in simple terms"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Concept loop")
    assert loop_info is not None
    assert loop_info["i"] == 0


def test_happy_path_node_validates(harness_factory):
    """Validate node rejects bad data at study concept step."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
    _walk_to_concept_loop(h)

    h.register_node(
        "2.1 Study concept",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("concept_name") else "must include concept_name",
        ),
    )

    r = h.submit({"notes": "forgot concept name"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"concept_name": "superposition"})
    assert r
    assert r.new_step == "2.2 Explain in simple terms"


def test_happy_path_node_archives(harness_factory):
    """Archive node writes concept results to SQLite table."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a", "b"]},
    )
    _walk_to_concept_loop(h)

    h.register_node(
        "2.2 Explain in simple terms",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"explanation": "string", "clarity": "string"}},
            archive={"table": "feynman_explanations"},
        ),
    )

    h.submit({})
    h.submit({"explanation": "like a coin flip", "clarity": "good"})
    h.submit_goto("2.0 Concept loop")
    h.submit({})
    h.submit({"explanation": "spooky action", "clarity": "ok"})

    rows = h.get_archived_rows("feynman_explanations")
    assert len(rows) == 2
    assert rows[0]["explanation"] == "like a coin flip"
    assert rows[1]["clarity"] == "ok"


# ================================================================
# Scenario 2: Not clear retry
# ================================================================


def test_not_clear_retry(harness_factory):
    """Learning monads in functional programming: explanation unclear twice before clicking."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["monads"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Functional Programming Concepts"})
    assert r
    r = h.submit({"concepts": ["Monads: composition of computations with context"]})
    assert r
    assert h.step == "2.1 Study concept"

    # First attempt: study, explain, not clear
    r = h.submit({"concept": "Monads", "source": "Haskell wiki, Philip Wadler's paper"})
    assert r
    r = h.submit({"explanation": "A monad is a monoid in the category of endofunctors"})
    assert r
    assert h.step == "2.3 Clear enough?"
    r = h.submit_goto("2.1 Study concept")
    assert r
    assert r.new_step == "2.1 Study concept"
    assert h.step == "2.1 Study concept"

    # Second attempt: still not clear (too abstract)
    r = h.submit({"concept": "Monads", "source": "Learn You a Haskell chapter 12"})
    assert r
    r = h.submit({"explanation": "A monad wraps a value and provides bind to chain operations"})
    assert r
    assert h.step == "2.3 Clear enough?"
    r = h.submit_goto("2.1 Study concept")
    assert r
    assert r.new_step == "2.1 Study concept"
    assert h.step == "2.1 Study concept"

    # Third attempt: clear (concrete analogy)
    r = h.submit({"concept": "Monads", "source": "Railway-oriented programming by Scott Wlaschin"})
    assert r
    r = h.submit({"explanation": "Think of a conveyor belt at a factory. Each station (function) does one thing. A monad is the belt itself -- it carries items between stations and handles errors (dropping items off the belt) so each station only worries about its own job."})
    assert r
    assert h.step == "2.3 Clear enough?"
    r = h.submit_goto("2.0 Concept loop")
    assert r
    assert h.step == "3.1 Create summary notes"


# ================================================================
# Scenario 3: Review rejected rework
# ================================================================


def test_review_rejected_rework(harness_factory):
    """Learning cryptography: public-key encryption unclear at first, symmetric encryption clear immediately."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["public_key_encryption", "symmetric_encryption"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Cryptography Fundamentals"})
    assert r
    r = h.submit({"concepts": ["Public-key (asymmetric) encryption", "Symmetric encryption (AES)"]})
    assert r

    # Concept 1: public-key encryption -- not clear, rework
    r = h.submit({"concept": "Public-key encryption", "source": "Diffie-Hellman paper"})
    assert r
    r = h.submit({"explanation": "Two keys: public encrypts, private decrypts, based on one-way functions"})
    assert r
    r = h.submit_goto("2.1 Study concept")
    assert r
    assert r.new_step == "2.1 Study concept"
    assert h.step == "2.1 Study concept"

    # Concept 1: clear on retry with better analogy
    r = h.submit({"concept": "Public-key encryption", "source": "Khan Academy RSA explainer"})
    assert r
    r = h.submit({"explanation": "Imagine a mailbox with a slot (public key) anyone can drop letters into, but only the owner has the key (private key) to open it. RSA works similarly -- multiplying two huge primes is easy, but factoring the product back is practically impossible."})
    assert r
    r = h.submit_goto("2.0 Concept loop")
    assert r
    assert r.new_step == "2.1 Study concept"
    assert h.step == "2.1 Study concept"

    # Concept 2: symmetric encryption -- clear first try
    r = h.submit({"concept": "Symmetric encryption (AES)", "source": "NIST AES specification"})
    assert r
    r = h.submit({"explanation": "Same key locks and unlocks. Like a diary with a combination lock -- you and your friend both know the combination. AES shuffles data through multiple rounds of substitution and permutation using that shared key."})
    assert r
    r = h.submit_goto("2.0 Concept loop")
    assert r
    assert h.step == "3.1 Create summary notes"


# ================================================================
# Scenario 4: Back to loop cross-phase fallback
# ================================================================


def test_back_to_loop_cross_phase_fallback(harness_factory):
    """Learning recursion: at summary, realize base case explanation was wrong, go back to fix."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["recursion"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Recursion in Computer Science"})
    assert r
    r = h.submit({"concepts": ["Recursion: base case, recursive case, call stack"]})
    assert r

    # Complete loop
    r = h.submit({"concept": "Recursion", "source": "SICP Chapter 1"})
    assert r
    r = h.submit({"explanation": "A function that calls itself with a smaller input until it hits a stopping condition"})
    assert r
    r = h.submit_goto("2.0 Concept loop")
    assert r
    assert h.step == "3.1 Create summary notes"

    # While writing summary, realize explanation omitted stack overflow risks
    r = h.goto("2.1 Study concept")
    assert r
    assert r.new_step == "2.1 Study concept"
    assert h.step == "2.1 Study concept"
    assert h.status == "running"

    # Redo the concept with stack overflow consideration
    r = h.submit({"concept": "Recursion", "source": "SICP + tail call optimization paper"})
    assert r
    r = h.submit({"explanation": "Like Russian nesting dolls: each doll opens to reveal a smaller one (recursive case) until you reach the tiny solid doll (base case). Without tail-call optimization, each opened doll stays in your hands (stack frame), and too many dolls means you drop them all (stack overflow)."})
    assert r
    assert h.step == "2.3 Clear enough?"


# ================================================================
# Scenario 5: Stop then resume
# ================================================================


def test_stop_then_resume(harness_factory):
    """Learning machine learning: stop during neural network explanation for lunch, resume after."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["gradient_descent", "backpropagation"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Neural Network Training"})
    assert r
    r = h.submit({"concepts": ["Gradient descent optimization", "Backpropagation algorithm"]})
    assert r
    r = h.submit({"concept": "Gradient descent", "source": "Andrew Ng's ML course, lecture 2"})
    assert r
    assert h.step == "2.2 Explain in simple terms"

    # Lunch break -- stop studying
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Explain in simple terms"

    # Back from lunch -- resume
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Explain in simple terms"

    # Continue from where we left off
    r = h.submit({"explanation": "Imagine hiking down a mountain in fog. You cannot see the bottom, but you feel the slope under your feet. You always step in the steepest downhill direction (gradient). Step size (learning rate) matters -- too big and you overshoot, too small and you never arrive."})
    assert r
    assert r.new_step == "2.3 Clear enough?"
    assert h.step == "2.3 Clear enough?"


# ================================================================
# Scenario 6: Skip a step
# ================================================================


def test_skip_a_step(harness_factory):
    """Learning databases: already know SQL basics, skip study; explain directly for review."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["sql_joins", "database_indexing"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Database Concepts"})
    assert r
    r = h.submit({"concepts": ["SQL JOINs", "Database Indexing (B-tree, hash)"]})
    assert r

    # Concept 1: SQL JOINs -- complete normally
    r = h.submit({"concept": "SQL JOINs", "source": "PostgreSQL documentation"})
    assert r
    r = h.submit({"explanation": "JOINs combine rows from two tables based on a matching column, like matching student IDs between an enrollment table and a grades table."})
    assert r
    r = h.submit_goto("2.0 Concept loop")
    assert r

    # Concept 2: Database indexing -- already studied, skip study and explain
    assert h.step == "2.1 Study concept"
    r = h.skip("Already studied B-tree indexing last semester in DB course")
    assert r
    assert h.step == "2.2 Explain in simple terms"
    r = h.skip("Can explain indexing from prior knowledge")
    assert r
    assert h.step == "2.3 Clear enough?"

    # Still need to resolve the LLM branch
    r = h.submit_goto("2.0 Concept loop")
    assert r
    assert h.step == "3.1 Create summary notes"


# ================================================================
# Scenario 7: Complete then reset
# ================================================================


def test_complete_then_reset(harness_factory):
    """Finish learning operating systems concepts, reset for networking topic."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["virtual_memory"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Operating Systems Internals"})
    assert r
    r = h.submit({"concepts": ["Virtual memory and page tables"]})
    assert r
    r = h.submit({"concept": "Virtual memory", "source": "OSTEP textbook, Chapter 18"})
    assert r
    r = h.submit({"explanation": "Like a librarian who pretends the library has infinite shelf space. When you request a book (memory address), the librarian (MMU) looks up the real shelf location (physical address) in an index (page table). If the book is in storage (disk), the librarian fetches it first (page fault)."})
    assert r
    r = h.submit_goto("2.0 Concept loop")
    assert r
    r = h.submit({"summary": "Virtual memory abstracts physical RAM using page tables, enabling isolation and the illusion of unlimited memory."})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Reset for a new topic: TCP/IP Networking
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Choose topic"
    assert h.status == "running"


# ================================================================
# Scenario 8: Back
# ================================================================


def test_back(harness_factory):
    """Learning compilers: realize topic needs narrowing, go back to choose more specific focus."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["lexical_analysis"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Compiler Design"})
    assert r
    assert h.step == "1.2 List concepts to learn"

    # Topic too broad -- go back and narrow it
    r = h.back()
    assert r
    assert h.step == "1.1 Choose topic"

    r = h.submit({"topic": "Compiler Frontend: Lexing and Parsing"})
    assert r
    r = h.submit({"concepts": ["Lexical analysis: tokenization with finite automata"]})
    assert r
    r = h.submit({"concept": "Lexical analysis", "source": "Dragon Book Chapter 3"})
    assert r
    assert h.step == "2.2 Explain in simple terms"

    # Need to re-read the source material before explaining
    r = h.back()
    assert r
    assert h.step == "2.1 Study concept"


# ================================================================
# Scenario 9: Goto to summary
# ================================================================


def test_goto_to_summary(harness_factory):
    """Already studied HTTP/REST in a prior session: jump to summary to consolidate notes."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["http_methods", "rest_constraints"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "RESTful API Design"})
    assert r
    r = h.submit({"concepts": ["HTTP methods (GET/POST/PUT/DELETE)", "REST architectural constraints"]})
    assert r

    # Already studied both concepts last week -- jump to summary
    r = h.goto("3.1 Create summary notes")
    assert r
    assert r.new_step == "3.1 Create summary notes"
    assert h.step == "3.1 Create summary notes"
    assert h.status == "running"

    r = h.submit({
        "summary": "REST uses HTTP verbs (GET=read, POST=create, PUT=update, DELETE=remove) with stateless requests, uniform interface, and resource-based URIs. Already understood from prior session.",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ================================================================
# Scenario 10: Modify YAML hot reload
# ================================================================


def test_modify_yaml_hot_reload(harness_factory):
    """Studying graph algorithms: add a peer review step to have a study partner verify explanations."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["dijkstra"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Graph Algorithms"})
    assert r
    assert h.step == "1.2 List concepts to learn"

    modified_yaml = """名称: Feynman Technique
描述: Modified with peer review step

步骤:
  - 1.1 Choose topic

  - 1.2 List concepts to learn

  - 2.0 Concept loop:
      遍历: "concepts"
      子步骤:
        - 2.1 Study concept
        - 2.2 Explain in simple terms
        - 2.3 Clear enough?:
            下一步:
              - 如果: "explanation is clear and complete"
                去: 2.0 Concept loop
              - 去: 2.1 Study concept

  - 3.05 Peer review:
      下一步: 3.1 Create summary notes

  - 3.1 Create summary notes

  - Done:
      类型: terminate
      原因: All concepts understood
"""
    h.reload_yaml(modified_yaml)

    r = h.goto("3.05 Peer review")
    assert r
    assert r.new_step == "3.05 Peer review"
    assert h.step == "3.05 Peer review"

    r = h.submit({
        "peer": "Study partner Marcus",
        "feedback": "Dijkstra explanation is clear but should mention it fails with negative edge weights",
    })
    assert r
    assert r.new_step == "3.1 Create summary notes"
    assert h.step == "3.1 Create summary notes"


# ================================================================
# Error boundaries
# ================================================================


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
    h.start()
    h.submit({})
    h.stop()
    assert h.status == "stopped"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
    h.start()
    h.goto("3.1 Create summary notes")
    h.submit({})
    assert h.status == "done"

    r = h.submit({})
    assert not r


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


# ================================================================
# Generic / cross-cutting tests
# ================================================================


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
    h.start()
    h.submit({"topic": "physics"})
    h.submit({"concepts_list": "gravity, force"})

    h.save_checkpoint("at_concept_loop")

    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Concept loop")
    assert h.step == "3.1 Create summary notes"

    restored = h.load_checkpoint("at_concept_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Study concept"
    assert "1.1 Choose topic" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
    h.start()
    assert h.step == "1.1 Choose topic"

    r = h.retry()
    assert r
    assert h.step == "1.1 Choose topic"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Choose topic"


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
    h.start()
    h.goto("3.1 Create summary notes")
    h.submit({})
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a", "b", "c"]},
    )
    _walk_to_concept_loop(h)

    loop_info = h.state.loop_state["2.0 Concept loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _complete_one_concept_clear(h)

    loop_info = h.state.loop_state["2.0 Concept loop"]
    assert loop_info["i"] == 1

    _complete_one_concept_clear(h)

    loop_info = h.state.loop_state["2.0 Concept loop"]
    assert loop_info["i"] == 2


def test_empty_concepts_skips_loop(harness_factory):
    """Empty concepts list causes loop to be skipped."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": []},
    )
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "3.1 Create summary notes"
    assert h.status == "running"


# ================================================================
# Turing Machine Condition Checker tests
# ================================================================


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
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
    h = harness_factory(
        "p7-feynman.yaml",
        loop_data={"concepts": ["a"]},
    )
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
