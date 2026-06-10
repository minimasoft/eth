"""Unit tests for 0002_cleanup_old_tables migration (Phase 38 cleanup)."""

from __future__ import annotations

import importlib
import inspect
from unittest.mock import patch

import pytest


MODULE_PATH = "eth_pipeline.alembic.versions.0002_cleanup_old_tables"


@pytest.fixture
def migration_module():
    """Import the 0002_cleanup_old_tables migration module."""
    return importlib.import_module(MODULE_PATH)


class TestMigration0002:
    """RED phase: these tests must fail before the migration file exists."""

    def test_import_succeeds(self) -> None:
        """Test 1: The migration module can be imported without ImportError."""
        mod = importlib.import_module(MODULE_PATH)
        assert mod is not None

    def test_revision_chain(self, migration_module) -> None:
        """Test 2: revision='0002' and down_revision='0001' are set correctly."""
        assert migration_module.revision == "0002", (
            f"Expected revision='0002', got '{migration_module.revision}'"
        )
        assert migration_module.down_revision == "0001", (
            f"Expected down_revision='0001', got '{migration_module.down_revision}'"
        )

    def test_upgrade_drops_tables_in_fk_safe_order(self, migration_module) -> None:
        """Test 3: upgrade() calls op.drop_table() in FK-safe order:
        event_participant, event_entity_link, reference, event, canonical_entity.
        """
        # Verify upgrade is a callable
        assert callable(migration_module.upgrade), "upgrade() must be callable"

        # Read the source to verify drop_table calls (does not execute them)
        source = inspect.getsource(migration_module.upgrade)

        # All five tables must appear in drop_table calls
        expected_order = [
            "event_participant",
            "event_entity_link",
            "reference",
            "event",
            "canonical_entity",
        ]

        # Find all op.drop_table('...') calls in order
        import re

        drop_calls = re.findall(r"op\.drop_table\(['\"](\w+)['\"]\)", source)
        assert len(drop_calls) >= 5, (
            f"Expected at least 5 drop_table calls, found {len(drop_calls)}: {drop_calls}"
        )

        # Verify the first 5 drop calls are in the expected FK-safe order
        for i, expected_table in enumerate(expected_order):
            assert drop_calls[i] == expected_table, (
                f"Drop order violation at position {i}: "
                f"expected '{expected_table}', got '{drop_calls[i]}'"
            )

    def test_downgrade_is_noop(self, migration_module) -> None:
        """Test 4: downgrade() is a no-op (contains only 'pass')."""
        assert callable(migration_module.downgrade), "downgrade() must be callable"

        source = inspect.getsource(migration_module.downgrade)

        # downgrade() body should only contain 'pass' (plus the docstring if any)
        # Extract the body after the signature line
        body_lines = [
            line.strip()
            for line in source.split("\n")[1:]  # skip the def line
            if line.strip() and not line.strip().startswith('"""')
        ]

        # After removing docstring, only 'pass' should remain
        non_pass = [line for line in body_lines if line != "pass"]
        assert len(non_pass) == 0, (
            f"downgrade() should only contain 'pass', found: {non_pass}"
        )

    def test_module_docstring(self, migration_module) -> None:
        """Test 5: Module-level docstring explains this is Phase 38 cleanup."""
        doc = migration_module.__doc__
        assert doc is not None, "Migration module must have a docstring"
        assert "phase 38" in doc.lower() or "cleanup" in doc.lower(), (
            f"Docstring should reference Phase 38 cleanup, got: {doc!r}"
        )