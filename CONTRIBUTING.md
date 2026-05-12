# Contributing to VIKI

Thanks for considering a contribution to VIKI! This project is built and
maintained by a community of contributors who share a single goal: a
local-first, private, autonomous AI agent that you can fully audit and control.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Project Principles](#project-principles)
3. [How Can I Contribute?](#how-can-i-contribute)
   * [Reporting Bugs](#reporting-bugs)
   * [Suggesting Enhancements](#suggesting-enhancements)
   * [Pull Requests](#pull-requests)
4. [Development Setup](#development-setup)
5. [Style Guides](#style-guides)
   * [Git Commit Messages](#git-commit-messages)
   * [Python Style](#python-style)
   * [JavaScript / React Style](#javascript--react-style)
6. [Need Help?](#need-help)

## Code of Conduct

This project is governed by the [Code of Conduct](./CODE_OF_CONDUCT.md). By
participating you agree to uphold it. Reports go through the channels listed
in that document.

## Project Principles

VIKI is built on the **Orythix Cognitive Architecture**:

* **Privacy first** — no telemetry, no external calls unless the user opts in.
* **Local execution** — primary path is Ollama and on-device LLMs.
* **Modular skills** — capabilities are gated by a security-first registry.
* **Air-gap capable** — every feature must be testable with no internet.

## How Can I Contribute?

### Reporting Bugs

* **Search first** — see if the bug is already filed in [Issues](https://github.com/Orythix/viki/issues).
* **Use the bug template** and include:
  * a clear title and description,
  * steps to reproduce,
  * environment (OS, Python version, Ollama model),
  * relevant `logs/viki.log` excerpts (with secrets redacted).

### Suggesting Enhancements

* Explain the **use case** — why is this feature needed and who benefits?
* Describe the **goal** — what should the feature do? Which existing skill
  or subsystem does it touch?
* If the change is non-trivial, open a Discussion first so we can align on
  design before code is written.

### Pull Requests

1. **Fork** the repo and create your branch from `main`.
2. **Keep PRs focused** — one logical change per PR. Split refactors from
   feature work.
3. **Write tests** — `pytest viki/tests/ -q` should stay green. New skills
   need at least one happy-path test.
4. **Run lint** — `ruff check viki` (CI runs the same).
5. **Update docs** — if you add or change a skill, configuration option, or
   public API, update the relevant `.md` file (often `README.md`,
   `ARCHITECTURE.md`, or `viki/SECURITY_SETUP.md`).
6. **Reference issues** — link any related issue in the PR description.
7. **Follow the PR template** — fill in summary and test plan.

## Development Setup

```bash
git clone https://github.com/Orythix/viki.git
cd viki
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# Unix:    source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # then fill in VIKI_API_KEY etc.
pytest viki/tests/ -q
```

Run the agent locally:

```bash
python viki/main.py            # CLI
python viki/api/server.py      # HTTP API
cd ui && npm install && npm run dev   # dashboard
```

## Style Guides

### Git Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

* `feat:` — a new feature
* `fix:` — a bug fix
* `docs:` — documentation only
* `style:` — formatting, no code change
* `refactor:` — refactoring without behavior change
* `test:` — adding or refactoring tests
* `chore:` — tooling, deps, CI

The repository ships a `commit-msg` hook that strips bot/IDE
`Co-authored-by:` trailers so history shows human authorship only. Enable it
locally with:

```bash
git config core.hooksPath .githooks
```

### Python Style

* Follow **PEP 8**; line length is **120** (see `pyproject.toml`).
* Use **type hints** on new public functions and class methods.
* Document non-trivial functions with docstrings (purpose, args, returns,
  raises). Avoid noise comments that just narrate what the code already says.
* Wrap blocking I/O in `asyncio.to_thread(...)` so the cognitive loop stays
  responsive.

### JavaScript / React Style

* Use functional components with React Hooks.
* Components must be responsive and follow the existing dark-mode HSL theme.
* Maintain the "Hologram" aesthetic for any new UI surfaces.

## Subprojects

Changes to **`security-lab/`** or **`qa-automation/`** should keep those folders **runnable on their own** (do not require importing private VIKI internals unless explicitly agreed). Use each subfolder’s `README.md` and tests as the contract. Docs index: [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md).

## Need Help?

* General questions → [GitHub Discussions](https://github.com/Orythix/viki/discussions)
* Bug reports → [GitHub Issues](https://github.com/Orythix/viki/issues)
* Security issues → see [`SECURITY.md`](./SECURITY.md) (private advisories only)

---

**VIKI: Virtual Intelligence, Real Evolution.**

---

*Runbook version: aligned with VIKI v8.0.0 (Industrial). Update this file when default ports, flags, or critical architecture patterns change.*
