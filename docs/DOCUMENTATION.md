# Documentation index

Central map of **first-party** docs in this monorepo (engineering playbooks under `playbooks/` are listed in that folder’s README).

## Core VIKI

| Document | Description |
|----------|-------------|
| [README.md](../README.md) | Product overview, quick start, Neural Forge bake (`viki-neural-forge` default Ollama tag), architecture summary |
| [docs/SETUP.md](../docs/SETUP.md) | Install, env, first run |
| [docs/VIKI_RUNBOOK.md](../docs/VIKI_RUNBOOK.md) | Operations, troubleshooting, RAG eval, boot evolution |
| [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) | System design, data flow, frontier wiring |
| [docs/ROADMAP.md](../docs/ROADMAP.md) | Restructure status, remaining engineering phases, future features |
| [docs/DOCKER.md](../docs/DOCKER.md) | Container run |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](../CHANGELOG.md) | Version history |
| [README_VIKI_PUBLIC.md](README_VIKI_PUBLIC.md) | Root README for **VIKI-public** mirrors (`readme_override` in export manifest) |
| [Repository visibility & public mirror](#repository-visibility-and-public-mirror) | Private **viki** vs **VIKI-public**, `scripts/export_public_mirror.py`, PowerShell push flow |
| [docs/SECURITY.md](../docs/SECURITY.md) | Security policy |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Community standards |
| [viki/SECURITY_docs/SETUP.md](../viki/SECURITY_docs/SETUP.md) | API keys, UI auth, capabilities |
| [viki/ARCHITECTURE_REFACTOR.md](../viki/ARCHITECTURE_REFACTOR.md) | Controller / pipeline refactor notes |

## UI

| Document | Description |
|----------|-------------|
| [ui/.env.example](../ui/.env.example) | Vite env template (`VITE_VIKI_API_KEY`, …) |

## Security lab (standalone)

| Document | Description |
|----------|-------------|
| [labs/security-lab/README.md](../labs/security-lab/README.md) | Lab overview |
| [labs/security-lab/docs/DEPLOYMENT.md](../labs/security-lab/docs/DEPLOYMENT.md) | Docker / local run |
| [labs/security-lab/docs/API.md](../labs/security-lab/docs/API.md) | REST API |
| [labs/security-lab/docs/THREAT_MODEL.md](../labs/security-lab/docs/THREAT_MODEL.md) | Threat model |
| [labs/security-lab/docs/SECURITY_CHECKLIST.md](../labs/security-lab/docs/SECURITY_CHECKLIST.md) | Pre-flight checklist |
| [labs/security-lab/docs/EXAMPLE_ATTACKS_AND_DEFENSES.md](../labs/security-lab/docs/EXAMPLE_ATTACKS_AND_DEFENSES.md) | Educational scenarios |

## QA automation (learning track)

| Document | Description |
|----------|-------------|
| [labs/qa-automation/README.md](../labs/qa-automation/README.md) | Multi-stack test tracks |
| [labs/qa-automation/docs/SYLLABUS.md](../labs/qa-automation/docs/SYLLABUS.md) | Curriculum |
| [labs/qa-automation/docs/STACK_INDEX.md](../labs/qa-automation/docs/STACK_INDEX.md) | Tool → path map |

## Evaluation

| Document | Description |
|----------|-------------|
| [viki/eval/README.md](../viki/eval/README.md) | RAG gold format, metrics, `run_rag_eval.py` |

## Engineering playbooks

See [playbooks/README.md](../playbooks/README.md) (upstream import + in-house waves + `megatron_lm/`).

---

## Repository visibility and public mirror

If the remote repository is **public**, **every branch is public**. Cloners can run `git fetch --all` and check out any branch. Putting “full” code only on `internal` / `full` / `develop` **does not hide it** from the internet.

To **actually** restrict who sees the full codebase, use one of these patterns.

### A. Private repo (simplest)

- Keep **one** private repository.
- Grant access only to maintainers.
- Optional: publish **releases** or **artifacts** without sharing the full tree.

**Branches (example):**

| Branch    | Role |
|-----------|------|
| `main`    | Release-ready, reviewed history (can still be *full* code—repo is private). |
| `develop` | Day-to-day integration (optional). |

This protects code because **the repo is private**, not because of branch names.

### B. Public “lite” repo + private “full” repo

- **Private repo** (e.g. **Orythix/viki**): complete source, issues, CI, secrets, experiments.
- **Public repo** (e.g. **Orythix/VIKI-public**): only what you allow—docs and reference files—without proprietary trees.

Sync options (pick one):

1. **Scripted export** — `scripts/export_public_mirror.py` copies an allow-list from private → a sibling folder (e.g. `../VIKI-public`), then you `git push` that folder to the public remote.
2. **`git subtree split`** — publish a subdirectory or branch into another repo (maintainers document exact commands).
3. **CI** — on tag or schedule, push a sanitized tree (no secrets in public CI vars).

Never commit secrets to the public repo; assume **full git history** there is readable forever.

### C. Single repo, public `main` only (advanced, still risky)

Tools like **git-subtree**, **sparse-checkout**, or **filter-repo** can maintain a branch that **only contains** a subset of files. **Risk:** one mistaken push can leak paths or history. Prefer **two repos** (B) unless you have strong release engineering.

### Two branches in one private repo only

This **organizes** work; it does **not** hide code from the public if the repo is public:

- `main` — stable, releasable.
- `develop` (or `next`) — ongoing integration before merge to `main`.

### Checklist before going public with a “lite” tree

- [ ] No API keys, tokens, or `.env` in history.
- [ ] No customer or personal data in `data/`, logs, or notebooks.
- [ ] License file matches what you redistribute.
- [ ] Root README on the public repo matches what is exported (use **`readme_override: docs/README_VIKI_PUBLIC.md`** so links are not broken).

### Summary

- **Branch split alone does not protect** a **public** repo.
- Use a **private** repository for the full codebase, and a **separate public** repository (or artifacts) for a curated subset.

### How to run the export (PowerShell)

Canonical implementation repo (**Orythix/viki**) should be **Private**; anonymous readers use **VIKI-public**.

1. **Configure:** copy `scripts/public_mirror.manifest.example.yaml` to `scripts/public_mirror.manifest.yaml` (gitignored) and edit `destination` + `include`.
2. **Export:**

```powershell
Set-Location "D:\My Projects\VIKI"
python scripts\export_public_mirror.py --dry-run
python scripts\export_public_mirror.py
```

3. **First push** from the destination (e.g. `D:\My Projects\VIKI-public`), using an **empty** public GitHub repo:

```powershell
Set-Location "D:\My Projects\VIKI-public"
git init
git branch -M main
git remote add origin https://github.com/Orythix/VIKI-public.git
git add .
git commit -m "Initial public mirror from VIKI export"
git push -u origin main
```

If **`remote origin already exists`**, use `git remote set-url origin https://github.com/Orythix/VIKI-public.git`. If **`git push` is rejected** because GitHub created an initial commit, use an empty repo or `git pull origin main --allow-unrelated-histories`, then push again.

Later updates: re-run **`export_public_mirror.py`**, then `git add -A`, `commit`, `push` from **VIKI-public**.

**Security before every public push:** search the export for secrets; ensure **`destination`** is **not** inside the private repo (the script refuses that layout).

---

*Runbook version: aligned with VIKI v8.3.0 (The Code Eternal). Update this file when default ports, flags, or critical architecture patterns change.*
