# Discrimination Proof Checklist for Health Guards

**Purpose**: Ensure new health guards include concrete failure discrimination evidence before merge, not just a checklist of completed steps.

## Scope

This checklist applies to new **production health guards** — automated checks that prevent bad data, misconfigured pipelines, or broken states from reaching production. This includes:

- Pipeline checks (e.g., `pipelines/check_*.py`)
- Monitor checks / health-artifact validations
- Rendered assertions in dashboards
- Workflow steps that gate production deployments

**Not included** (per the parent charter):
- Registry system for guards
- Retrofitting old guards
- Running arbitrary tests from PR prose
- Generic mutation or meta-test frameworks

## The Four Required Items

For each new health guard, the PR body must include all four items:

1. **Guard ID**: A unique identifier for the guard (e.g., `check_fidelity_ordering`, `curve_default_guard`, `lineage_snapshot_guard`)

2. **Concrete Broken Scenario**: A specific, reproducible condition that the guard detects and blocks. This must be a real defect state, not a hypothetical.

3. **Broken-State Test/Command + Observed Result**:
   - The exact command or test that demonstrates the guard catching the defect
   - The observed output showing the guard blocking/failing on the broken state

4. **Correct-State Test/Command + Observed Result**:
   - The exact command or test that demonstrates the guard passing when the defect is fixed
   - The observed output showing the guard accepting the correct state

### Presence Enforcement

- Each item must contain non-empty, non-placeholder content
- A blank entry or placeholder (e.g., "TBD", "TODO", "describe here") fails validation
- The CLI checker (`pipelines/check_pr_discrimination.py`) enforces presence

## Applicability: What Counts as a New Guard?

A change is considered a "new production guard" when it introduces:

1. **New pipeline check**: Any new `pipelines/check_*.py` or similar validation script
2. **New monitor check**: Any new health-artifact validation in `ops/` or `pipelines/`
3. **New rendered assertion**: Any new guard in `tools/guard_harness.mjs` or equivalent
4. **New workflow gate**: Any new step in `.github/workflows/*.yml` that enforces health

**Ambiguous cases**: If the change's applicability is unclear (e.g., a refactor that indirectly affects guards, or a test-only change), the reviewer must declare applicability with a reason. The checker does not auto-detect applicability — it accepts a reviewer declaration.

## Checker Behavior

The CLI tool `pipelines/check_pr_discrimination.py` validates:

- **Presence**: All four required fields are present and non-empty
- **Applicability**: If the diff touches guard-related files, the checklist is required; otherwise the tool accepts an explicit applicability reason (e.g., "docs-only change")

### Usage

```bash
python3 pipelines/check_pr_discrimination.py \
  --body-file /path/to/pr_body.md \
  --diff-file /path/to/diff.txt
```

Exit codes:
- `0` — Pass: checklist complete OR explicit applicability reason provided
- `1` — Fail: required checklist items missing/blank/placeholder

### CI Integration

In `.github/workflows/preview.yml`, add a step that runs the checker on PR diffs:

```yaml
- name: Check PR discrimination proof
  run: |
    python3 pipelines/check_pr_discrimination.py \
      --body-file /path/to/pr_body.md \
      --diff-file /path/to/diff.txt
```

The checker runs with read-only permissions and never executes contributor code.

## Reviewer Responsibilities

1. **Validate the checklist**: Ensure each of the four items is concrete and meaningful
2. **Run the guard**: Independently execute the guard against the named broken fixture
3. **Reject vacuous tests**: If the "broken state" test passes (or the "correct state" test fails), the proof is invalid
4. **Record evidence**: Save the actual commands, exit codes, expected vs observed results, base/head SHA, and broken-state discrimination evidence

## What This Is NOT

- **Not a registry**: This does not create a catalog of all guards
- **Not retroactive**: Does not require adding discrimination proof to existing guards
- **Not a test executor**: Does not run arbitrary tests from PR descriptions
- **Not a mutation framework**: Does not generate broken states to test guards

## Deferrals (Out of Scope)

- Registry system for health guards
- Retrofitting discrimination proof to existing guards
- Generic broken-state test runners
- Automated proof generation

---

*This checklist enforces presence + independent discrimination review. See the parent JEG-139 for rationale and scope details.*
