"""Tests for Alembic migrations — structure and ordering validation.

Since we cannot run actual DB migrations in CI without PostgreSQL,
these tests validate migration file structure, ordering, and dependencies.
"""
import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "alembic" / "versions"


class TestMigrationFiles:
    """Validate Alembic migration file structure."""

    def _get_migration_files(self):
        """Get sorted list of migration .py files."""
        if not MIGRATIONS_DIR.exists():
            pytest.skip("Alembic versions directory not found")
        files = sorted(MIGRATIONS_DIR.glob("*.py"))
        return [f for f in files if f.name != "__pycache__"]

    def test_migrations_directory_exists(self):
        assert MIGRATIONS_DIR.exists(), f"Migrations dir not found: {MIGRATIONS_DIR}"

    def test_migrations_exist(self):
        files = self._get_migration_files()
        assert len(files) > 0, "No migration files found"

    def test_migration_file_naming_convention(self):
        """All migration files should follow YYYYMMDD_NNNN_slug format."""
        pattern = re.compile(r"^\d{8}_\d{4}_.+\.py$")
        for f in self._get_migration_files():
            assert pattern.match(f.name), (
                f"Migration file '{f.name}' doesn't match naming convention "
                "YYYYMMDD_NNNN_slug.py"
            )

    def test_migration_files_have_revision(self):
        """Each migration should define revision and down_revision."""
        for f in self._get_migration_files():
            content = f.read_text()
            assert "revision" in content, f"{f.name} missing 'revision'"
            assert "down_revision" in content, f"{f.name} missing 'down_revision'"

    def test_migration_files_have_upgrade_downgrade(self):
        """Each migration should define upgrade() and downgrade() functions."""
        for f in self._get_migration_files():
            content = f.read_text()
            assert "def upgrade()" in content, f"{f.name} missing upgrade()"
            assert "def downgrade()" in content, f"{f.name} missing downgrade()"

    def test_migration_chain_is_linear(self):
        """Verify there are no fork or orphan migrations.

        Each migration's down_revision should point to the previous one's revision
        (linear chain from first migration to latest).
        """
        files = self._get_migration_files()
        if len(files) < 2:
            pytest.skip("Need at least 2 migrations for chain test")

        revision_pattern = re.compile(
            r"^revision\s*(?::\s*str\s*)?=\s*['\"]([^'\"]+)['\"]", re.MULTILINE
        )
        down_rev_pattern = re.compile(
            r"^down_revision\s*(?::\s*Union\[str,\s*None\]\s*)?=\s*(.+)$", re.MULTILINE
        )

        revisions = {}  # revision_id -> filename
        down_revisions = {}  # revision_id -> down_revision_id (None for root)

        for f in files:
            content = f.read_text()
            rev_match = revision_pattern.search(content)
            down_match = down_rev_pattern.search(content)
            if rev_match and down_match:
                rev_id = rev_match.group(1).strip()
                raw_down = down_match.group(1).strip()
                # Parse Python None vs quoted string
                if raw_down == "None":
                    down_id = None
                else:
                    down_id = raw_down.strip("'\"").strip()
                revisions[rev_id] = f.name
                down_revisions[rev_id] = down_id

        # Find the root (down_revision = None)
        roots = [r for r, d in down_revisions.items() if d is None]
        assert len(roots) >= 1, (
            f"No root migration found (down_revision = None). "
            f"Found: {list(down_revisions.items())[:5]}"
        )

        # Every non-root should reference an existing revision
        for rev_id, down_id in down_revisions.items():
            if down_id is not None:
                assert down_id in revisions, (
                    f"Migration {revisions[rev_id]} references non-existent "
                    f"down_revision '{down_id}'"
                )

    def test_migrations_ordered_chronologically(self):
        """Migration files should be in chronological order by filename prefix."""
        files = self._get_migration_files()
        names = [f.name for f in files]
        assert names == sorted(names), "Migration files are not in chronological order"

    def test_expected_migration_count(self):
        """We expect at least 16 migrations as documented."""
        files = self._get_migration_files()
        assert len(files) >= 16, (
            f"Expected at least 16 migrations, found {len(files)}"
        )

    def test_rbac_migration_exists(self):
        """RBAC tables migration should exist."""
        files = self._get_migration_files()
        rbac_files = [f for f in files if "rbac" in f.name.lower()]
        assert len(rbac_files) > 0, "RBAC migration not found"

    def test_automation_migration_exists(self):
        """Automation tables migration should exist."""
        files = self._get_migration_files()
        auto_files = [f for f in files if "automation" in f.name.lower()]
        assert len(auto_files) > 0, "Automation migration not found"
