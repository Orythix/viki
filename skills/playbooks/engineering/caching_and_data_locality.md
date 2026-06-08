# Caching and Data Locality

> Guides agents through cache layering, invalidation, and consistency tradeoffs.

## Overview

Caching and Data Locality provides production discipline for engineers who need predictable outcomes under real operational constraints.
Use this playbook to keep decisions explicit, prove behavior with evidence, and reduce regression risk while shipping.

## When to Use

- The change affects reliability, safety, or operability in production.
- Multiple teams or services depend on the resulting behavior.
- You need a repeatable process that survives handoffs and incidents.
- Reviewers require objective evidence, not claims.

## Process

1. **Frame domain concerns** - align scope with cache layering, invalidation, and consistency tradeoffs.
   - Capture assumptions, invariants, and explicit non-goals in repository docs.
   - Identify measurable indicators that prove behavior is correct.
2. **Instrument and baseline** - gather current-state evidence before changing implementation.
   - Run tests, lint/type checks, and benchmarks to establish baseline metrics.
   - Save command output and artifacts for before/after comparison.
3. **Implement in small verified steps** - apply one meaningful transformation at a time.
   - Keep commits narrowly scoped with one clear intent.
   - Re-run focused verification after each step and stop on drift.
4. **Harden edge and failure paths** - design for partial failure, retries, and rollback.
   - Ensure errors are explicit and observable with correlation identifiers.
   - Validate behavior under degraded dependencies and invalid inputs.
5. **Close with operational proof** - publish evidence and owner-assigned follow-ups.
   - Document tradeoffs, deferred debt, and remediation owners.
   - Link dashboards, migrations, manifests, or runbooks needed for support.

## Rationalizations

| Excuse | Why it's wrong |
|---|---|
| "This change is obvious, we can skip process." | Hidden assumptions are where outages and regressions start. |
| "We will add tests and observability later." | Delayed verification turns simple fixes into incident response. |
| "A larger batch is faster than incremental steps." | Big diffs reduce review quality and make rollback expensive. |
| "If CI passes, production risk is covered." | CI alone rarely captures runtime dependencies and failure modes. |

## Red Flags

- No baseline metrics or command outputs captured before implementation.
- Process steps completed out of order to meet a deadline.
- Failure-handling behavior undocumented or inconsistent across interfaces.
- Verification relies on subjective checks instead of reproducible evidence.

## Verification

- Provide exact commands executed (tests, lint/type checks, benchmark or load runs) and their outputs.
- Show files produced or updated as proof artifacts (migration scripts, dashboards, manifests, runbooks, changelog entries).
- Record measurable before/after metrics relevant to this domain and explain any regressions.
- Confirm rollback or mitigation path was tested or rehearsed with documented outcomes.

### Domain Checks

- Confirm design decisions align with cache layering, invalidation, and consistency tradeoffs.
- Verify assumptions against real workload patterns and incident history.
- Review interfaces for backward compatibility and ownership.
- Ensure diagnostics can prove runtime behavior without ad-hoc debugging.

### Execution Notes

- Prefer deterministic workflows over manual one-off operations.
- Keep human approval points explicit for high-risk actions.
- Treat deprecations, migrations, and rollback as first-class tasks.
- Update related documentation in the same change set.
