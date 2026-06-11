"""
Code connector — extracts codebase knowledge from local git repositories.

Supports:
  path: /absolute/path/to/cloned/repo   (primary — fast, no network)
  url:  https://github.com/org/repo      (auto-clone to ~/.one-context/repos/)

Works with any git host: GitHub, GitLab, Bitbucket, self-hosted.

config keys (from onecontext.yaml under the 'code' source):
  repos               list of dicts — each has 'path' or 'url'
  summarize_at        "service" | "module" | "file"  (default: module)
  include             glob patterns  (default: common source extensions)
  exclude             glob patterns  (default: tests, build artifacts, etc.)
  git_history_months  int  (0 = skip history, default: 12)
"""
import os
import fnmatch
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

import git

from hygiene.models import RawContent
from hygiene.processors.code_summariser import summarise_modules_batch
from connectors.base import BaseConnector

DEFAULT_INCLUDE = [
    "**/*.py", "**/*.ts", "**/*.js", "**/*.tsx", "**/*.jsx",
    "**/*.java", "**/*.go", "**/*.rb", "**/*.cs", "**/*.scala",
    "**/openapi.yaml", "**/openapi.yml",
]
DEFAULT_EXCLUDE = [
    "**/tests/**", "**/test/**", "**/spec/**",
    "**/migrations/**", "**/node_modules/**", "**/__pycache__/**",
    "**/dist/**", "**/build/**", "**/.git/**", "**/vendor/**",
    "**/*.lock", "**/*.min.js", "**/*.generated.*",
]

MAX_FILE_BYTES = 100_000     # skip files larger than this
MAX_FILES_PER_MODULE = 20    # cap files sent to LLM per module

CACHE_DIR = Path.home() / ".one-context" / "repos"


class GitHubExtractor(BaseConnector):
    """Named GitHubExtractor for backward-compat; registered as 'code' and 'github'."""

    def validate_config(self, config: dict) -> None:
        if "repos" not in config or not config["repos"]:
            raise ValueError("code source requires at least one entry under 'repos'")
        for entry in config["repos"]:
            if "path" not in entry and "url" not in entry:
                raise ValueError(f"each repo entry must have 'path' or 'url': {entry}")
            if "path" in entry and not Path(entry["path"]).exists():
                raise ValueError(f"repo path does not exist: {entry['path']}")

    def extract(self, config: dict) -> list[RawContent]:
        self.validate_config(config)
        include = config.get("include", DEFAULT_INCLUDE)
        exclude = config.get("exclude", DEFAULT_EXCLUDE)
        summarize_at = config.get("summarize_at", "module")
        git_history_months = config.get("git_history_months", 12)

        items: list[RawContent] = []
        for entry in config["repos"]:
            repo_path = self._resolve_path(entry)
            print(f"  [code] {repo_path.name} ({repo_path})...")

            code_items = self._extract_code(repo_path, summarize_at, include, exclude)
            items.extend(code_items)
            print(f"  [code] {repo_path.name}: {len(code_items)} code chunks")

            if git_history_months > 0:
                history_items = self._extract_git_history(repo_path, git_history_months)
                items.extend(history_items)
                print(f"  [code] {repo_path.name}: {len(history_items)} commits from git history")

        return items

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def _resolve_path(self, entry: dict) -> Path:
        if "path" in entry:
            return Path(entry["path"]).expanduser().resolve()
        return self._ensure_cloned(entry["url"])

    def _ensure_cloned(self, url: str) -> Path:
        slug = url.rstrip("/").split("/")[-1].removesuffix(".git")
        dest = CACHE_DIR / slug
        if dest.exists():
            print(f"    pulling latest for {slug}...")
            subprocess.run(
                ["git", "-C", str(dest), "pull", "--ff-only", "-q"],
                check=False, capture_output=True,
            )
        else:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            print(f"    cloning {url}...")
            subprocess.run(
                ["git", "clone", "--depth=200", url, str(dest)],
                check=True,
            )
        return dest

    # ------------------------------------------------------------------
    # Code extraction
    # ------------------------------------------------------------------

    def _extract_code(
        self,
        repo_path: Path,
        summarize_at: str,
        include: list[str],
        exclude: list[str],
    ) -> list[RawContent]:
        # 1. Collect matching files
        matched = self._collect_files(repo_path, include, exclude)
        if not matched:
            print(f"    no files matched include/exclude patterns")
            return []

        # 2. Group into modules
        modules = self._group_into_modules(repo_path, matched, summarize_at)

        # 3. Read contents
        modules_content: dict[str, dict[str, str]] = {}
        for module_key, file_paths in modules.items():
            modules_content[module_key] = {}
            for fp in file_paths[:MAX_FILES_PER_MODULE]:
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                    modules_content[module_key][fp.relative_to(repo_path).as_posix()] = text
                except OSError:
                    pass

        print(f"    {len(matched)} files → {len(modules)} modules, summarising...")

        # 4. Summarise
        summaries = summarise_modules_batch(
            repo=repo_path.name,
            modules=modules_content,
            progress_callback=lambda done, total: (
                print(f"    {done}/{total} modules summarised...")
                if done % 5 == 0 or done == total else None
            ),
        )

        # 5. Convert to RawContent
        items = []
        for module_key, summary in summaries.items():
            file_list = list(modules_content.get(module_key, {}).keys())
            items.append(RawContent(
                id=f"code:{repo_path.name}:{module_key}",
                source="code",
                title=f"{repo_path.name} / {module_key}",
                body=self._format_body(summary, file_list),
                url="",
                last_updated=datetime.now(timezone.utc),
                metadata={
                    "repo": repo_path.name,
                    "repo_path": str(repo_path),
                    "module_path": module_key,
                    "content_type": summary.get("primary_content_type", "business_flow"),
                    "capabilities": summary.get("capabilities", []),
                    "integrations": summary.get("integrations", []),
                    "entities": summary.get("entities", []),
                    "files": file_list,
                },
            ))
        return items

    def _collect_files(self, repo_path: Path, include: list[str], exclude: list[str]) -> list[Path]:
        matched = []
        for f in repo_path.rglob("*"):
            if not f.is_file():
                continue
            if f.stat().st_size > MAX_FILE_BYTES:
                continue
            rel = f.relative_to(repo_path).as_posix()
            if self._matches_any(rel, exclude):
                continue
            if self._matches_any(rel, include):
                matched.append(f)
        return matched

    def _group_into_modules(
        self, repo_path: Path, files: list[Path], summarize_at: str
    ) -> dict[str, list[Path]]:
        groups: dict[str, list[Path]] = {}
        for f in files:
            rel = f.relative_to(repo_path).as_posix()
            parts = rel.split("/")
            if summarize_at == "service":
                key = repo_path.name
            elif summarize_at == "file":
                key = rel
            else:  # module — group by top-level directory
                key = parts[0] if len(parts) > 1 else "."
            groups.setdefault(key, []).append(f)
        return groups

    @staticmethod
    def _format_body(summary: dict, file_paths: list[str]) -> str:
        parts = [summary.get("summary", "")]
        if summary.get("capabilities"):
            parts.append("Capabilities: " + "; ".join(summary["capabilities"]))
        if summary.get("integrations"):
            parts.append("Integrations: " + ", ".join(summary["integrations"]))
        if summary.get("entities"):
            parts.append("Domain entities: " + ", ".join(summary["entities"]))
        parts.append("Files: " + ", ".join(file_paths[:10]))
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Git history
    # ------------------------------------------------------------------

    def _extract_git_history(self, repo_path: Path, months: int) -> list[RawContent]:
        since = datetime.now(timezone.utc) - timedelta(days=months * 30)
        items = []
        try:
            repo = git.Repo(repo_path)
            try:
                ref = repo.active_branch
            except TypeError:
                ref = repo.head.commit   # detached HEAD — iterate from current commit
            for commit in repo.iter_commits(ref, merges=True):
                committed_dt = commit.committed_datetime
                if committed_dt.tzinfo is None:
                    committed_dt = committed_dt.replace(tzinfo=timezone.utc)
                else:
                    committed_dt = committed_dt.astimezone(timezone.utc)
                if committed_dt < since:
                    break
                items.append(RawContent(
                    id=f"code:{repo_path.name}:commit:{commit.hexsha[:8]}",
                    source="code",
                    title=f"[Shipped] {commit.summary}",
                    body=commit.message.strip()[:2000],
                    url="",
                    last_updated=committed_dt,
                    author=commit.author.name,
                    metadata={
                        "content_type": "shipped_feature",
                        "repo": repo_path.name,
                        "sha": commit.hexsha[:8],
                    },
                ))
        except (git.InvalidGitRepositoryError, git.GitCommandError) as e:
            print(f"    WARNING: could not read git history: {e}")
        return items

    # ------------------------------------------------------------------
    # Pattern matching
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_any(rel_path: str, patterns: list[str]) -> bool:
        filename = rel_path.split("/")[-1]
        for pattern in patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            simple = pattern.lstrip("*/")
            if simple and fnmatch.fnmatch(filename, simple):
                return True
            if "**" in pattern:
                mid = pattern.strip("*").strip("/")
                if mid and f"/{mid}/" in f"/{rel_path}/":
                    return True
        return False
