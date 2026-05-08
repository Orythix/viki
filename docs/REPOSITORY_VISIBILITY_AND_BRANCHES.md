# Repository visibility: public “overview” vs private full code

## Important limitation

If the remote repository is **public**, **every branch is public**. Cloners can run `git fetch --all` and check out any branch. Putting “full” code only on `internal` / `full` / `develop` **does not hide it** from the internet.

To **actually** restrict who sees the full codebase, use one of these patterns.

## Recommended patterns

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

### B. Public “lite” repo + private “full” repo (matches your goal)

- **Private repo** (e.g. `viki-full`): complete source, issues, CI, secrets, experiments.
- **Public repo** (e.g. `viki`): only what you want others to see—enough to **understand** the agent, run a **demo**, or read **docs**—**without** proprietary modules, keys, or internal paths.

Sync options (pick one):

1. **Manual / scripted export** — script copies an allow-list of paths from private → public; you run it when you cut a public update.
2. **`git subtree split`** — publish a subdirectory or branch from the private repo into the public repo (maintainers document the exact commands).
3. **CI** — on tag or schedule, pipeline builds a **sanitized tarball** or pushes to the public repo (no secrets in CI vars on the public side).

Never commit secrets to the public repo; assume **full git history** there is readable forever.

### C. Single repo, public `main` only (advanced, still risky)

Tools like **git-subtree**, **sparse-checkout**, or **filter-repo** can maintain a branch that **only contains** a subset of files. **Risk:** one mistaken push can leak paths or history. **Operational cost** is high. Prefer **two repos** (B) unless you have strong release engineering.

## If you still want two branches in one private repo

This only works for **organizing** work, not for hiding from the public (repo must stay **private**):

- `main` — stable, releasable.
- `develop` (or `next`) — full ongoing work before merge to `main`.

External contributors still need **private** access to see `develop`.

## Checklist before going public with a “lite” tree

- [ ] No API keys, tokens, or `.env` in history.
- [ ] No customer or personal data in `data/`, logs, or notebooks.
- [ ] License file matches what you redistribute.
- [ ] `README` states what is omitted and points to issue tracker / contact for full product if applicable.

## Summary

- **Branch split alone does not protect** a **public** repo.
- Use a **private** repository for the full codebase, and optionally a **separate public** repository (or release artifacts) for a **curated subset** others are allowed to see.

---

## How to do it (two repos + export script)

This repo includes **`scripts/export_public_mirror.py`**. It copies an **allow-list** of files and folders into a **second directory** (usually a **sibling** folder like `../VIKI-public`). That directory becomes your **public** Git tree; this repo stays **private** (full code).

### 1. Keep this clone private

On GitHub/GitLab: set the **canonical** VIKI repo to **Private** (full history, all branches).

### 2. Create an empty public repository

Create a **new**, **Public** repo (e.g. `viki` or `viki-docs`) with **no** README (or delete the default commit after).

### 3. Configure the manifest

```powershell
Set-Location "D:\My Projects\VIKI"
Copy-Item scripts\public_mirror.manifest.example.yaml scripts\public_mirror.manifest.yaml
notepad scripts\public_mirror.manifest.yaml   # or your editor: set destination + include
```

`scripts/public_mirror.manifest.yaml` is **gitignored** so your list stays local if you prefer.

### 4. Export

Use the same Python you use for VIKI (venv if you have one: `.\.venv\Scripts\Activate.ps1` first).

```powershell
Set-Location "D:\My Projects\VIKI"
python scripts\export_public_mirror.py --dry-run
python scripts\export_public_mirror.py
```

Open the **destination** folder (default from the example manifest: `D:\My Projects\VIKI-public`). Confirm there is **no** `data/`, `.env`, keys, or proprietary trees unless you explicitly included them.

The example manifest sets **`readme_override: docs/README_VIKI_PUBLIC.md`** so GitHub shows a **root `README.md`** whose links match the thin public tree (the full `README.md` points at `viki/…` and `scripts/…` files that are not exported and look “broken” on **VIKI-public**).

### 5. Initialize Git in the destination (first time only)

Create an **empty** public repo on GitHub (no README / no `.gitignore` template), or you will need to `git pull` / merge before the first push.

Replace **`Orythix`** and **`viki-public`** with your org and repo name. Use **HTTPS** (below) or **`git@github.com:Orythix/viki-public.git`** for SSH.

```powershell
Set-Location "D:\My Projects\VIKI-public"
git init
git branch -M main
git config user.email "you@example.com"    # once per machine, or omit if already set globally
git config user.name "Your Name"
git remote add origin https://github.com/Orythix/viki-public.git
git add .
git commit -m "Initial public mirror from VIKI export"
git push -u origin main
```

**If `git push` is rejected** because GitHub created an initial commit: either use an empty repo, or run  
`git pull origin main --allow-unrelated-histories`, resolve if needed, then `git push -u origin main`.

Later updates: re-run **`export_public_mirror.py`**, then from `VIKI-public` run `git add -A`, `git commit -m "Sync public mirror"`, `git push`.

### 6. Security checks before every public push

- Search the export for secrets: API keys, tokens, emails, internal hostnames.
- Ensure **`destination`** is **not** inside the private repo (the script refuses that path layout).

An automated agent **cannot** log in to your GitHub account or push for you; steps 1, 2, and 5 require your browser and credentials.
