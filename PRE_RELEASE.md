# Pre-release guide: taking VIKI public

Use this checklist when preparing a pre-release (alpha/beta) for public users.

## Before you release

1. **Version**
   - Bump version in [pyproject.toml](pyproject.toml) (e.g. `7.4.0` or `7.3.1`).
   - For a clear pre-release, you can use a pre-release suffix: `7.4.0rc1` or `7.4.0b1` (PEP 440).
   - Update [README.md](README.md) version badge and any “v7.3.0” references if needed.
   - Ensure [CHANGELOG.md](CHANGELOG.md) has an entry for this version and date.

2. **Security and defaults**
   - [.env.example](.env.example) is up to date; no secrets.
   - Docs state that `VIKI_API_KEY` is required for the API and should be generated (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
   - [viki/SECURITY_SETUP.md](viki/SECURITY_SETUP.md) and [SECURITY.md](SECURITY.md) reflect current behavior.

3. **Docs for first-time users**
   - [README.md](README.md) Quick Start is accurate (clone, venv, `.env`, run CLI or API + UI).
   - [DOCKER.md](DOCKER.md) is correct if you offer Docker.
   - Known limitations or “beta” caveats are mentioned (e.g. in README or below).

## Release steps

### 1. Tag and push

From repo root, with a clean working tree:

```bash
git tag -a v7.3.0 -m "Release v7.3.0"
git push origin v7.3.0
```

Use your actual version (e.g. `v7.4.0rc1` for a release candidate). If you use the GitHub Actions workflow in `.github/workflows/release.yml`, pushing a tag will create a GitHub Release automatically.

### 2. Create a GitHub Release (if not automated)

- Repo: **Releases** → **Draft a new release**.
- Choose the tag you pushed (e.g. `v7.3.0`).
- Title: e.g. `VIKI v7.3.0 (Pre-release)`.
- Description: copy the relevant section from [CHANGELOG.md](CHANGELOG.md) for this version; add a short “Pre-release” note and link to README / install instructions.
- Optionally attach a source zip (GitHub often offers “Source code (zip)” from the tag).
- Check **Pre-release** if this is alpha/beta.
- Publish.

### 3. Optional: Publish to PyPI (for `pip install viki-sdi`)

If you want users to install with `pip install viki-sdi`:

- Install build: `pip install build twine`.
- Build: `python -m build`.
- Upload to Test PyPI first: `twine upload --repository testpypi dist/*`.
- Then production: `twine upload dist/*` (requires PyPI account and token).

Pre-release versions (e.g. `7.4.0rc1`) are supported by PyPI; users can `pip install viki-sdi==7.4.0rc1`.

### 4. Optional: Docker image

If you use Docker:

- Build and tag: `docker build -t your-registry/viki-api:7.3.0 .`
- Push: `docker push your-registry/viki-api:7.3.0`
- Document the image name and tag in [DOCKER.md](DOCKER.md) and README.

### 5. Announce and support

- Announce where your users are (e.g. GitHub Discussions, Twitter, Discord).
- Point to **Install**: clone + Quick Start in README, or one-line install ([install.sh](install.sh) / Windows equivalent), or `pip install viki-sdi` if published.
- Point to **Issues**: “Report bugs or suggest features at [GitHub Issues](https://github.com/YOUR_ORG/viki/issues).”
- If you have a roadmap or known issues, link to it (e.g. in README or a ROADMAP.md).

## One-line install (for public)

Your README already references:

- **Unix**: `curl -fsSL https://raw.githubusercontent.com/toozuuu/viki/main/install.sh | bash`
- **Windows**: `irm https://raw.githubusercontent.com/toozuuu/viki/main/install.ps1 | iex` (if you add or keep install.ps1)

Ensure the default branch (e.g. `main`) is stable for new users, or point the script to a release tag (e.g. `.../v7.3.0/install.sh`) for a fixed version.

## Pre-release disclaimer (for README)

You can add a short note for public users, for example:

> **Pre-release:** VIKI is in active development. We welcome feedback and bug reports via [GitHub Issues](https://github.com/YOUR_ORG/viki/issues). Use in production at your own risk; ensure you set `VIKI_API_KEY` and follow [SECURITY_SETUP.md](viki/SECURITY_SETUP.md).

Replace `YOUR_ORG` with your GitHub org or username.
