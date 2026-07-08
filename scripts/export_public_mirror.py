"""
Export an allow-listed subset of the repo to a second folder (public mirror).

Does not push to GitHub — run git commands yourself in the destination.

  python scripts/export_public_mirror.py
  python scripts/export_public_mirror.py --manifest scripts/public_mirror.manifest.yaml
  python scripts/export_public_mirror.py --dry-run

See docs/DOCUMENTATION.md § Repository visibility and public mirror.
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise SystemExit("Manifest must be a YAML mapping.")
    return data


def _ignore_factory(patterns: Sequence[str]):
    pats = list(patterns)

    def _ignore(_src: str, names: list[str]) -> list[str]:
        ignored: list[str] = []
        for name in names:
            for pat in pats:
                if fnmatch.fnmatch(name, pat):
                    ignored.append(name)
                    break
        return ignored

    return _ignore


def _resolve_destination(dest: str) -> Path:
    p = Path(dest)
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    return p


def _dest_inside_repo(dest: Path) -> bool:
    try:
        dest.relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


def export_mirror(manifest_path: Path, dry_run: bool) -> int:
    m = _load_manifest(manifest_path)
    dest = _resolve_destination(str(m.get("destination") or "").strip() or "../VIKI-public")
    include = m.get("include") or []
    if not isinstance(include, list) or not include:
        raise SystemExit("Manifest must define a non-empty `include` list.")

    ignore_globs = m.get("ignore_globs") or ["__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"]
    if not isinstance(ignore_globs, list):
        raise SystemExit("`ignore_globs` must be a list.")

    if _dest_inside_repo(dest):
        print(
            "ERROR: destination is inside the private repo. Use a sibling folder (e.g. ../VIKI-public).",
            file=sys.stderr,
        )
        return 2

    print(f"Manifest : {manifest_path}")
    print(f"Dest     : {dest}")
    readme_override = (m.get("readme_override") or "").strip()

    print(f"Items    : {len(include)}")
    if readme_override:
        print(f"README   : {readme_override} -> README.md (after include list)")

    if dry_run:
        for item in include:
            src = REPO_ROOT / item
            print(f"  [dry-run] would sync {item} -> {dest / item} (exists={src.exists()})")
        if readme_override:
            ro = REPO_ROOT / readme_override
            print(f"  [dry-run] would write README.md <- {readme_override} (exists={ro.is_file()})")
        return 0

    dest.mkdir(parents=True, exist_ok=True)

    ign = _ignore_factory(ignore_globs)
    for item in include:
        src = REPO_ROOT / item
        if not src.exists():
            print(f"  SKIP (missing): {item}", file=sys.stderr)
            continue
        dst = dest / item
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst, ignore=ign, dirs_exist_ok=False)
        else:
            shutil.copy2(src, dst)
        print(f"  OK {item}")

    if readme_override:
        ro = REPO_ROOT / readme_override
        if not ro.is_file():
            print(f"  FAIL readme_override not found: {readme_override}", file=sys.stderr)
            return 3
        shutil.copy2(ro, dest / "README.md")
        print(f"  OK README.md <- {readme_override}")

    print("Done. Next: cd to destination, git init (once), add remote, commit, push.")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export public subset of VIKI to another directory.")
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="YAML manifest (default: scripts/public_mirror.manifest.yaml or .example.yaml)",
    )
    p.add_argument("--dry-run", action="store_true", help="Print planned copies only.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.manifest:
        mp = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    else:
        preferred = REPO_ROOT / "scripts" / "public_mirror.manifest.yaml"
        example = REPO_ROOT / "scripts" / "public_mirror.manifest.example.yaml"
        mp = preferred if preferred.exists() else example
    if not mp.is_file():
        print(
            "No manifest found. Copy scripts/public_mirror.manifest.example.yaml to "
            "scripts/public_mirror.manifest.yaml and edit, or pass --manifest.",
            file=sys.stderr,
        )
        return 1
    return export_mirror(mp, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
