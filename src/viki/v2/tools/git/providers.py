"""Git provider using shell."""

from __future__ import annotations

from ..shell.providers import LocalShellProvider, ShellProvider


class GitProvider:
    """Git operations via shell."""

    def __init__(self, shell: ShellProvider | None = None):
        self.shell = shell or LocalShellProvider()

    async def run_git(self, args: str, workdir: str | None = None) -> str:
        result = await self.shell.run(f"git {args}", workdir)
        if result.returncode != 0:
            raise RuntimeError(f"git {args} failed: {result.stderr}")
        return result.stdout

    async def status(self, workdir: str | None = None) -> dict:
        out = await self.run_git("status --porcelain", workdir)
        return {"clean": not out.strip(), "raw": out}

    async def log(self, limit: int = 10, workdir: str | None = None) -> list[dict]:
        out = await self.run_git(
            f"log -{limit} --pretty=format:%H|%an|%ad|%s --date=short", workdir
        )
        commits = []
        for line in out.strip().splitlines():
            if line:
                parts = line.split("|", 3)
                if len(parts) == 4:
                    commits.append(
                        {
                            "hash": parts[0],
                            "author": parts[1],
                            "date": parts[2],
                            "message": parts[3],
                        }
                    )
        return commits

    async def branches(self, workdir: str | None = None) -> dict:
        out = await self.run_git("branch -a", workdir)
        branches = []
        current = None
        for line in out.strip().splitlines():
            name = line.strip().lstrip("* ").strip()
            if line.startswith("*"):
                current = name
            branches.append(name)
        return {"current": current, "branches": branches}

    async def diff(self, target: str = "HEAD", workdir: str | None = None) -> str:
        return await self.run_git(f"diff {target}", workdir)

    async def add(self, files: str = ".", workdir: str | None = None) -> str:
        return await self.run_git(f"add {files}", workdir)

    async def commit(self, message: str, workdir: str | None = None) -> str:
        return await self.run_git(f'commit -m "{message}"', workdir)

    async def push(
        self, remote: str = "origin", branch: str | None = None, workdir: str | None = None
    ) -> str:
        args = f"push {remote}"
        if branch:
            args += f" {branch}"
        return await self.run_git(args, workdir)

    async def pull(
        self, remote: str = "origin", branch: str | None = None, workdir: str | None = None
    ) -> str:
        args = f"pull {remote}"
        if branch:
            args += f" {branch}"
        return await self.run_git(args, workdir)

    async def remote_url(self, remote: str = "origin", workdir: str | None = None) -> str:
        return (await self.run_git(f"remote get-url {remote}", workdir)).strip()
