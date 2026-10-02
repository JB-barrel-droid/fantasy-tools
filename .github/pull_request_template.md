# Pull Request Template

## Summary

<!-- Brief description of what this PR changes or fixes -->

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor
- [ ] Documentation
- [ ] Other: <!-- describe -->

---

## Discrimination Proof Checklist (Required for New Health Guards)

**If this PR adds a new production health guard, complete all four items below. See `docs/health/discrimination-proof-checklist.md` for details.**

### 1. Guard ID

<!-- Unique identifier for the guard (e.g., check_fidelity_ordering, curve_default_guard) -->

### 2. Concrete Broken Scenario

<!-- Specific, reproducible condition that this guard detects and blocks. Must be a real defect state, not a hypothetical. -->

### 3. Broken-State Test/Command + Observed Result

<!--
Exact command or test that demonstrates the guard catching the defect.
Include the observed output showing the guard blocking/failing on the broken state.
-->

### 4. Correct-State Test/Command + Observed Result

<!--
Exact command or test that demonstrates the guard passing when the defect is fixed.
Include the observed output showing the guard accepting the correct state.
-->

---

## Applicability Declaration (Required)

**If this PR does NOT add a new health guard, declare why the checklist above is not applicable:**

- [ ] This is a docs-only change
- [ ] This is a test-only change (no production guard added)
- [ ] This is a refactor with no guard behavior change
- [ ] Other: <!-- explain -->

---

## Testing

<!-- Describe how this change was tested. Include commands run and results. -->

## Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Tests added/updated (if applicable)
- [ ] Documentation updated (if applicable)

---

*For new health guards: Ensure the four checklist items above contain concrete evidence, not placeholders. The reviewer will independently run the guard against the named broken fixture to verify discrimination.*
