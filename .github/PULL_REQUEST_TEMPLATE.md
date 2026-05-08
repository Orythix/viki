<!--
Thanks for contributing to VIKI! Please fill in the sections below.
Keep PRs focused on one logical change. Split refactors from feature work.
-->

## Summary

<!-- One or two sentences. What does this PR do and why? -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (behavior, config, or API change)
- [ ] Documentation only
- [ ] Tooling / CI / chore

## Linked issues

Closes #
Related to #

## Test plan

<!-- How did you verify this? Paste commands and key output. Reviewers should
     be able to reproduce these checks locally. -->

- [ ] `ruff check viki` is clean
- [ ] `pytest viki/tests/ -q` passes locally
- [ ] If a skill changed: added or updated a test in `viki/tests/`
- [ ] If a config option changed: documented in `README.md` or `viki/SECURITY_SETUP.md`
- [ ] If user-facing: screenshots / CLI output included below

```text
# Paste relevant test or run output here.
```

## Screenshots / recordings

<!-- For UI changes only. Drop them here. -->

## Checklist

- [ ] My changes follow [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- [ ] I have not committed secrets, real API keys, or personal data
- [ ] Commits use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, …)
- [ ] No `Co-authored-by:` trailers from bots / IDE assistants
