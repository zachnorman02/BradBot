"""Unit tests for /permissions conditional grant -- the merge of the old
set_eligibility(True) + assign into one step. grant marks the user eligible
itself now (no separate "mark eligible first" command required), but should
otherwise preserve assign's override/blocking/deferral behavior exactly.

Calls the command's underlying callback directly with lightweight fakes, no
pytest-asyncio dependency: asyncio.run() per test, same pattern as the rest
of this suite.
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import commands.permissions.conditional_commands as conditional_commands
from commands.permissions.conditional_commands import PermissionsConditionalGroup


def _run(coro):
    return asyncio.run(coro)


def _call_grant(interaction, user, role):
    group = PermissionsConditionalGroup()
    cmd = group.get_command("grant")
    return cmd.callback(group, interaction, user, role)


def _interaction(guild):
    return SimpleNamespace(
        guild=guild,
        user=SimpleNamespace(id=1, display_name="Actor"),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _role(role_id, name="role"):
    return SimpleNamespace(id=role_id, name=name, mention=f"<@&{role_id}>")


def _guild(roles_by_id):
    return SimpleNamespace(id=1, get_role=lambda rid: roles_by_id.get(rid))


def test_grant_errors_when_role_not_configured():
    role = _role(10)
    guild = _guild({})
    interaction = _interaction(guild)
    user = SimpleNamespace(id=20, mention="<@20>", roles=[])

    with patch.object(conditional_commands.db, "get_conditional_role_config", return_value=None), \
         patch.object(conditional_commands, "send_error") as send_error_mock, \
         patch.object(conditional_commands.db, "mark_conditional_role_eligible") as mark_mock:
        _run(_call_grant(interaction, user, role))

    send_error_mock.assert_awaited_once()
    mark_mock.assert_not_called()


def test_grant_with_active_override_force_adds_without_marking_eligible():
    role = _role(10)
    guild = _guild({})
    interaction = _interaction(guild)
    user = SimpleNamespace(id=20, mention="<@20>", roles=[], add_roles=AsyncMock())

    with patch.object(conditional_commands.db, "get_conditional_role_config", return_value={"blocking_role_ids": [], "deferral_role_ids": []}), \
         patch.object(conditional_commands.db, "has_conditional_role_override", return_value=True), \
         patch.object(conditional_commands.db, "unmark_conditional_role_eligible") as unmark_mock, \
         patch.object(conditional_commands.db, "mark_conditional_role_eligible") as mark_mock, \
         patch.object(conditional_commands, "send_success") as send_success_mock:
        _run(_call_grant(interaction, user, role))

    user.add_roles.assert_awaited_once()
    unmark_mock.assert_called_once()
    mark_mock.assert_not_called()  # override path never touches the eligibility flag
    send_success_mock.assert_awaited_once()


def test_grant_marks_eligible_even_when_blocked():
    blocking_role = _role(99)
    role = _role(10)
    guild = _guild({99: blocking_role})
    interaction = _interaction(guild)
    user = SimpleNamespace(id=20, mention="<@20>", roles=[blocking_role], add_roles=AsyncMock())

    with patch.object(conditional_commands.db, "get_conditional_role_config", return_value={"blocking_role_ids": [99], "deferral_role_ids": []}), \
         patch.object(conditional_commands.db, "has_conditional_role_override", return_value=False), \
         patch.object(conditional_commands.db, "mark_conditional_role_eligible") as mark_mock, \
         patch.object(conditional_commands, "send_error") as send_error_mock:
        _run(_call_grant(interaction, user, role))

    mark_mock.assert_called_once()  # eligibility is still recorded...
    user.add_roles.assert_not_awaited()  # ...but the role is withheld
    send_error_mock.assert_awaited_once()
    assert "blocking roles" in send_error_mock.call_args[0][1]


def test_grant_defers_when_user_has_deferral_role():
    deferral_role = _role(55, "Pending")
    role = _role(10)
    guild = _guild({55: deferral_role})
    interaction = _interaction(guild)
    user = SimpleNamespace(id=20, mention="<@20>", roles=[deferral_role], add_roles=AsyncMock())

    with patch.object(conditional_commands.db, "get_conditional_role_config", return_value={"blocking_role_ids": [], "deferral_role_ids": [55]}), \
         patch.object(conditional_commands.db, "has_conditional_role_override", return_value=False), \
         patch.object(conditional_commands.db, "mark_conditional_role_eligible") as mark_mock:
        _run(_call_grant(interaction, user, role))

    user.add_roles.assert_not_awaited()
    # Called twice: the unconditional up-front mark, then again with deferred notes.
    assert mark_mock.call_count == 2
    interaction.followup.send.assert_awaited_once()
    assert "deferred" in interaction.followup.send.call_args[0][0].lower()


def test_grant_succeeds_and_adds_role_when_clear():
    role = _role(10)
    guild = _guild({})
    interaction = _interaction(guild)
    user = SimpleNamespace(id=20, mention="<@20>", roles=[], add_roles=AsyncMock())

    with patch.object(conditional_commands.db, "get_conditional_role_config", return_value={"blocking_role_ids": [], "deferral_role_ids": []}), \
         patch.object(conditional_commands.db, "has_conditional_role_override", return_value=False), \
         patch.object(conditional_commands.db, "mark_conditional_role_eligible") as mark_mock, \
         patch.object(conditional_commands, "send_success") as send_success_mock:
        _run(_call_grant(interaction, user, role))

    user.add_roles.assert_awaited_once()
    assert mark_mock.call_count == 2  # up-front mark + "Assigned directly by admin" notes
    send_success_mock.assert_awaited_once()
