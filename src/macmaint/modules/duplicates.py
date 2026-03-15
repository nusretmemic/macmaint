"""Duplicate file detection module.

Uses SHA256 hash + file-size matching to find duplicate files.
Files are hashed in parallel using ThreadPoolExecutor for performance.
Supports dry-run mode and persists scan history for trend analysis.
"""

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from macmaint.models.issue import Issue, IssueSeverity, IssueCategory, FixAction, ActionType


# Directories that are almost always safe to skip
_SKIP_DIRS = frozenset({
    ".git", "node_modules", ".Trash", "Library/Caches",
    ".cache", "__pycache__", ".tox", ".venv", "venv",
    ".DS_Store",
})

# File extensions to always skip (system internals, package DBs, etc.)
_SKIP_EXTENSIONS = frozenset({
    ".DS_Store", ".localized",
})


class DuplicateScanner:
    """Find duplicate files using SHA256 hash + size matching.

    Detection strategy
    ------------------
    1.  Collect all candidate files (size >= min_size_mb, not in skip dirs).
    2.  Group by file size — only files sharing a size can be duplicates.
    3.  For each size-group with 2+ files, compute SHA256 in parallel.
    4.  Files with identical hashes are duplicates.
    5.  Within each duplicate group sort by mtime desc; the newest file is
        recommended for keeping (keep_recommended=True).

    Args:
        config: Dict from ``Config.get_module_config("duplicates")``.
    """

    # History file stores summary records of past scans for trend analysis.
    HISTORY_FILE = Path.home() / ".macmaint" / "duplicate_history.json"

    def __init__(self, config: Dict):
        self.min_size_bytes = int(config.get("min_size_mb", 1) * 1024 * 1024)
        self.max_workers = int(config.get("max_workers", 4))
        self._default_paths: Optional[List[str]] = config.get("scan_paths")  # None → built at scan time

    # ── Public API ─────────────────────────────────────────────────────────────

    def scan(
        self,
        paths: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> Tuple[Dict, List[Issue]]:
        """Scan *paths* for duplicate files.

        Args:
            paths:   Directories to scan.  ``None`` → use configured defaults
                     (Downloads, Documents, Desktop, Pictures, Music, Movies).
            dry_run: If True, produce results but do not record history.

        Returns:
            Tuple of (metrics_dict, issues_list).
        """
        t0 = time.monotonic()

        scan_paths = self._resolve_paths(paths)
        files = self._collect_files(scan_paths)
        files_scanned = len(files)

        if files_scanned == 0:
            metrics = self._empty_metrics(0, 0.0)
            return metrics, []

        hash_map = self._hash_files_parallel(files)
        groups = self._build_groups(hash_map)

        elapsed = time.monotonic() - t0

        total_duplicates = sum(g["count"] - 1 for g in groups)  # extra copies
        total_wasted_mb = sum(g["wasted_mb"] for g in groups)

        metrics = {
            "total_duplicates": total_duplicates,
            "duplicate_groups": groups,
            "duplicate_groups_count": len(groups),
            "total_wasted_space_mb": round(total_wasted_mb, 2),
            "scan_duration_seconds": round(elapsed, 2),
            "files_scanned": files_scanned,
            "scan_paths": [str(p) for p in scan_paths],
            "dry_run": dry_run,
        }

        issues = self._build_issues(groups)

        if not dry_run:
            self._save_history(metrics)

        return metrics, issues

    # ── History ────────────────────────────────────────────────────────────────

    @classmethod
    def load_history(cls, days: int = 30) -> List[Dict]:
        """Return recent scan history records (up to *days* old).

        Each record has keys: scanned_at, files_scanned, duplicate_groups_count,
        total_duplicates, total_wasted_space_mb, scan_duration_seconds.
        """
        if not cls.HISTORY_FILE.exists():
            return []
        try:
            with open(cls.HISTORY_FILE) as fh:
                records = json.load(fh)
            if not isinstance(records, list):
                return []
            cutoff = datetime.now().timestamp() - days * 86400
            return [
                r for r in records
                if isinstance(r, dict) and
                datetime.fromisoformat(r.get("scanned_at", "1970-01-01")).timestamp() >= cutoff
            ]
        except Exception:
            return []

    # ── Private helpers ────────────────────────────────────────────────────────

    def _resolve_paths(self, paths: Optional[List[str]]) -> List[Path]:
        """Return validated Path objects to scan."""
        home = Path.home()

        if paths:
            raw = paths
        elif self._default_paths:
            raw = self._default_paths
        else:
            raw = [
                str(home / "Downloads"),
                str(home / "Documents"),
                str(home / "Desktop"),
                str(home / "Pictures"),
                str(home / "Music"),
                str(home / "Movies"),
            ]

        result: List[Path] = []
        for p in raw:
            expanded = Path(p).expanduser().resolve()
            if not expanded.exists():
                continue
            # Safety: restrict to home directory
            try:
                expanded.relative_to(home)
            except ValueError:
                continue
            result.append(expanded)
        return result

    def _collect_files(self, scan_paths: List[Path]) -> List[Path]:
        """Recursively collect files >= min_size_bytes, skipping hidden/system dirs."""
        collected: List[Path] = []
        seen: set = set()  # avoid symlink loops / overlapping paths

        for root in scan_paths:
            try:
                for path in root.rglob("*"):
                    # Skip non-files
                    if not path.is_file() or path.is_symlink():
                        continue

                    # Skip if any component is in the skip set
                    parts = set(path.parts)
                    if parts & _SKIP_DIRS:
                        continue

                    # Skip by extension
                    if path.suffix in _SKIP_EXTENSIONS:
                        continue

                    # Deduplicate by inode (handles hard links)
                    try:
                        st = path.stat()
                    except (OSError, PermissionError):
                        continue

                    if st.st_size < self.min_size_bytes:
                        continue

                    inode_key = (st.st_dev, st.st_ino)
                    if inode_key in seen:
                        continue
                    seen.add(inode_key)

                    collected.append(path)
            except (OSError, PermissionError):
                continue

        return collected

    def _hash_files_parallel(self, files: List[Path]) -> Dict[str, List[Path]]:
        """Hash files in parallel; return {hash: [paths]} for groups with 2+ files.

        Optimisation: group by size first — files with different sizes cannot
        be duplicates, so we only hash files that share a size with another file.
        """
        # Group by size
        size_groups: Dict[int, List[Path]] = {}
        for f in files:
            try:
                sz = f.stat().st_size
            except (OSError, PermissionError):
                continue
            size_groups.setdefault(sz, []).append(f)

        # Only hash size groups with 2+ files
        candidates = [f for group in size_groups.values() if len(group) >= 2 for f in group]

        if not candidates:
            return {}

        hash_map: Dict[str, List[Path]] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_to_path = {pool.submit(self._sha256, f): f for f in candidates}
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                digest = future.result()
                if digest is not None:
                    hash_map.setdefault(digest, []).append(path)

        # Keep only groups with 2+ files
        return {h: paths for h, paths in hash_map.items() if len(paths) >= 2}

    @staticmethod
    def _sha256(path: Path) -> Optional[str]:
        """Compute SHA256 of *path* in 64 KB chunks.  Returns None on error."""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except (OSError, PermissionError):
            return None

    def _build_groups(self, hash_map: Dict[str, List[Path]]) -> List[Dict]:
        """Convert hash_map to structured duplicate groups sorted by wasted space desc."""
        groups: List[Dict] = []

        for digest, paths in hash_map.items():
            # Get file metadata
            file_entries: List[Dict] = []
            size_bytes = 0
            for p in paths:
                try:
                    st = p.stat()
                    size_bytes = st.st_size
                    mtime = datetime.fromtimestamp(st.st_mtime)
                    age_days = (datetime.now() - mtime).days
                    file_entries.append({
                        "path": str(p),
                        "size_mb": round(st.st_size / (1024 * 1024), 3),
                        "modified_date": mtime.strftime("%Y-%m-%d %H:%M"),
                        "age_days": age_days,
                        "keep_recommended": False,  # set below
                    })
                except (OSError, PermissionError):
                    continue

            if len(file_entries) < 2:
                continue

            # Sort newest first — keep the newest (index 0)
            file_entries.sort(key=lambda e: e["modified_date"], reverse=True)
            file_entries[0]["keep_recommended"] = True

            size_mb = round(size_bytes / (1024 * 1024), 3)
            count = len(file_entries)
            # Wasted space = (copies - 1) × size
            wasted_mb = round(size_mb * (count - 1), 3)

            groups.append({
                "hash": digest[:16],  # truncated for display
                "size_mb": size_mb,
                "count": count,
                "wasted_mb": wasted_mb,
                "files": file_entries,
            })

        # Largest wasted space first
        groups.sort(key=lambda g: g["wasted_mb"], reverse=True)
        return groups

    def _build_issues(self, groups: List[Dict]) -> List[Issue]:
        """Create one Issue per duplicate group."""
        issues: List[Issue] = []
        for group in groups:
            wasted = group["wasted_mb"]
            severity = (
                IssueSeverity.WARNING
                if wasted >= 100
                else IssueSeverity.INFO
            )
            # Paths recommended for deletion (all except keep_recommended)
            delete_paths = [
                f["path"] for f in group["files"] if not f["keep_recommended"]
            ]
            count = group["count"]
            size_mb = group["size_mb"]
            short_hash = group["hash"][:8]
            issue_id = f"duplicates_{short_hash}"

            # Example representative name from the kept file
            kept_name = Path(group["files"][0]["path"]).name

            issues.append(Issue(
                id=issue_id,
                title=f"Duplicate files: {kept_name} ({count} copies, {wasted:.1f} MB wasted)",
                description=(
                    f"{count} identical copies of a {size_mb:.1f} MB file detected. "
                    f"Keeping the newest copy and deleting {count - 1} duplicate(s) "
                    f"would free {wasted:.1f} MB."
                ),
                severity=severity,
                category=IssueCategory.DISK,
                fix_actions=[
                    FixAction(
                        action_type=ActionType.DELETE_FILES,
                        description=f"Delete {count - 1} duplicate copy/copies of {kept_name}",
                        details={
                            "paths": delete_paths,
                            "risk_level": "low",
                            "estimated_space_freed_mb": wasted,
                        },
                        safe=True,
                        requires_confirmation=True,
                    )
                ],
                metrics={
                    "hash": group["hash"],
                    "size_mb": size_mb,
                    "copies": count,
                    "wasted_mb": wasted,
                    "files": group["files"],
                    "delete_paths": delete_paths,
                },
            ))
        return issues

    @staticmethod
    def _empty_metrics(files_scanned: int, elapsed: float) -> Dict:
        return {
            "total_duplicates": 0,
            "duplicate_groups": [],
            "duplicate_groups_count": 0,
            "total_wasted_space_mb": 0.0,
            "scan_duration_seconds": round(elapsed, 2),
            "files_scanned": files_scanned,
            "scan_paths": [],
            "dry_run": False,
        }

    def _save_history(self, metrics: Dict) -> None:
        """Append a compact summary record to the history file."""
        record = {
            "scanned_at": datetime.now().isoformat(),
            "files_scanned": metrics["files_scanned"],
            "duplicate_groups_count": metrics["duplicate_groups_count"],
            "total_duplicates": metrics["total_duplicates"],
            "total_wasted_space_mb": metrics["total_wasted_space_mb"],
            "scan_duration_seconds": metrics["scan_duration_seconds"],
        }
        try:
            self.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            records: List[Dict] = []
            if self.HISTORY_FILE.exists():
                try:
                    with open(self.HISTORY_FILE) as fh:
                        records = json.load(fh)
                    if not isinstance(records, list):
                        records = []
                except Exception:
                    records = []
            records.append(record)
            # Keep last 365 records
            records = records[-365:]
            with open(self.HISTORY_FILE, "w") as fh:
                json.dump(records, fh, indent=2)
        except Exception:
            pass
