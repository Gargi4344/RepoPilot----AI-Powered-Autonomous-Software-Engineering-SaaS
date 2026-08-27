from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from app.models import ProjectAnalysis

IGNORED_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "dist", "build", ".next", "coverage"}
LANGUAGES = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cs": "C#", ".rb": "Ruby", ".php": "PHP",
}
MANIFESTS = {"pyproject.toml", "requirements.txt", "package.json", "go.mod", "Cargo.toml", "pom.xml", "build.gradle"}
TODO_PATTERN = re.compile(r"\b(?:TODO|FIXME|XXX)\b[:\s-]*(.*)", re.IGNORECASE)


class RepositoryAnalyzer:
    """Performs local, read-only repository discovery for Phase 1."""

    def analyze(self, root: Path) -> ProjectAnalysis:
        root = root.resolve()
        if not root.is_dir():
            raise ValueError(f"Repository path does not exist: {root}")
        if not (root / ".git").exists():
            raise ValueError("Repository path must be an already-cloned Git repository")

        languages: Counter[str] = Counter()
        manifests: list[str] = []
        test_directories: set[str] = set()
        todo_items: list[str] = []
        source_files = 0
        ignored_files = 0

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(root)
            if any(part in IGNORED_DIRECTORIES for part in relative.parts):
                ignored_files += 1
                continue
            if file_path.name in MANIFESTS:
                manifests.append(relative.as_posix())
            language = LANGUAGES.get(file_path.suffix.lower())
            if language:
                languages[language] += 1
                source_files += 1
            if any(part.lower() in {"test", "tests", "__tests__"} for part in relative.parts[:-1]):
                test_directories.add(relative.parent.as_posix())
            if file_path.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"}:
                todo_items.extend(self._todos(file_path, relative))

        tools = self._detect_tools(root, manifests)
        language_summary = ", ".join(f"{name} ({count})" for name, count in languages.most_common()) or "no supported source language"
        summary = f"{source_files} supported source files; primary languages: {language_summary}."
        return ProjectAnalysis(
            root=str(root), languages=dict(languages), manifests=sorted(manifests),
            readme_present=(root / "README.md").is_file() or (root / "readme.md").is_file(),
            test_directories=sorted(test_directories), todo_items=todo_items[:100],
            source_files=source_files, ignored_files=ignored_files, detected_tools=tools, summary=summary,
        )

    @staticmethod
    def _todos(file_path: Path, relative: Path) -> list[str]:
        try:
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return []
        findings = []
        for line_number, line in enumerate(lines, start=1):
            match = TODO_PATTERN.search(line)
            if match:
                detail = match.group(1).strip() or "Unspecified follow-up"
                findings.append(f"{relative.as_posix()}:{line_number}: {detail}")
        return findings

    @staticmethod
    def _detect_tools(root: Path, manifests: list[str]) -> list[str]:
        detected: set[str] = set()
        files = {Path(item).name for item in manifests}
        if "pyproject.toml" in files or "requirements.txt" in files:
            detected.update({"pytest", "ruff"})
        if "package.json" in files:
            detected.update({"npm", "eslint"})
        if "go.mod" in files:
            detected.add("go test")
        if (root / ".github" / "workflows").is_dir():
            detected.add("GitHub Actions")
        return sorted(detected)
