"""Unit tests for the auto-role-rule naming + enable/disable scheme:
generate_role_rule_name (the display label derived from trigger+add/remove
roles) and database.add_role_rule's upsert logic (reenable an exact match,
otherwise retire whichever row is active for that trigger and insert a new
one). See scripts/migrate.py Migration037 and the design discussion this
implements.

No real DB -- execute_query itself is mocked per test, same approach as the
rest of this suite uses for anything that would otherwise need a live
connection pool.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.permissions.helpers import generate_role_rule_name
from database import db


def _role(name):
    return SimpleNamespace(name=name)


def test_generate_role_rule_name_includes_trigger_and_both_lists():
    trigger = _role("Verified")
    add = [_role("lvl 0")]
    remove = [_role("Unverified")]
    name = generate_role_rule_name(trigger, add, remove)
    assert name == "Verified +lvl 0 -Unverified"


def test_generate_role_rule_name_omits_empty_lists():
    trigger = _role("Verified")
    assert generate_role_rule_name(trigger, [], []) == "Verified"
    assert generate_role_rule_name(trigger, [_role("A")], []) == "Verified +A"
    assert generate_role_rule_name(trigger, [], [_role("B")]) == "Verified -B"


def test_generate_role_rule_name_truncates_to_100_chars():
    trigger = _role("Trigger")
    many_roles = [_role(f"VeryLongRoleName{i}") for i in range(10)]
    name = generate_role_rule_name(trigger, many_roles, [])
    assert len(name) <= 100
    assert name.endswith("...")


def test_add_role_rule_reenables_exact_name_match_in_place():
    """Reconfiguring back to a combo that already exists (active or not)
    updates that row and sets enabled=TRUE, rather than inserting a
    duplicate. Call order: MAX(id) (always computed), then the name lookup,
    then -- here -- the in-place UPDATE."""
    mock_exec = MagicMock(side_effect=[
        [(7,)],   # SELECT COALESCE(MAX(id), 0) ...
        [(42,)],  # SELECT id ... WHERE rule_name = %s -> found existing row
        None,     # the UPDATE itself (fetch=False)
    ])
    with patch.object(db, "execute_query", mock_exec):
        db.add_role_rule(1, "Verified +lvl 0", 100, [200], [])

    queries = [c.args[0] for c in mock_exec.call_args_list]
    assert mock_exec.call_count == 3
    assert "SELECT id FROM app.role_rules" in queries[1]
    assert "UPDATE app.role_rules" in queries[2]
    assert "enabled = TRUE" in queries[2]
    assert "INSERT INTO" not in queries[2]


def test_add_role_rule_disables_old_row_and_inserts_new_combo():
    """A combo never seen before for this trigger retires whichever row is
    currently active for that trigger, then inserts the new one enabled."""
    mock_exec = MagicMock(side_effect=[
        [(7,)],  # SELECT COALESCE(MAX(id), 0) ...
        [],      # SELECT id ... WHERE rule_name = %s -> no existing row with this exact name
        None,    # UPDATE ... SET enabled = FALSE WHERE trigger_role_id = %s AND enabled = TRUE
        None,    # INSERT the new row
    ])
    with patch.object(db, "execute_query", mock_exec):
        db.add_role_rule(1, "Verified +lvl 0 -Unverified", 100, [200], [300])

    queries = [c.args[0] for c in mock_exec.call_args_list]
    assert mock_exec.call_count == 4
    assert "SET enabled = FALSE" in queries[2]
    assert "trigger_role_id = %s AND enabled = TRUE" in queries[2]
    assert "INSERT INTO app.role_rules" in queries[3]
    assert "TRUE" in queries[3]  # inserted as enabled


def test_add_role_rule_skips_insert_entirely_on_reenable_path():
    """The reenable path only ever issues an UPDATE -- no disable-sweep and
    no INSERT, since it's the same row being touched."""
    mock_exec = MagicMock(side_effect=[
        [(7,)],
        [(42,)],  # name lookup finds an existing row -> update path
        None,
    ])
    with patch.object(db, "execute_query", mock_exec):
        db.add_role_rule(1, "Verified", 100, [], [])
    assert mock_exec.call_count == 3
    assert "INSERT" not in mock_exec.call_args_list[-1].args[0]
