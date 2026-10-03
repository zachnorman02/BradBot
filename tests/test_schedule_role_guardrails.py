"""Integration-ish unit tests for ScheduleRoleModal's hierarchy and
role-deny guardrails -- the fix that made /permissions role schedule match
/permissions role set and /permissions role temp instead of silently
bypassing both checks. The guardrail logic lives in the modal's on_submit
now (schedule itself just opens the modal), so these tests build the modal
directly and simulate a submission.

Calls on_submit directly (bypassing the Discord dispatch/permission-check
layer, which isn't what's under test here) with lightweight fakes, same
pattern as the other mocked-db/mocked-object tests in this suite. No
pytest-asyncio dependency: asyncio.run() per test.
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import commands.permissions.modals as modals
from commands.permissions.modals import ScheduleRoleModal


class FakeRole:
    def __init__(self, id_, position, name="role", managed=False, default=False):
        self.id = id_
        self.position = position
        self.name = name
        self.mention = f"<@&{id_}>"
        self.managed = managed
        self._default = default

    def is_default(self):
        return self._default

    def __le__(self, other):
        return self.position <= other.position

    def __lt__(self, other):
        return self.position < other.position

    def __ge__(self, other):
        return self.position >= other.position

    def __gt__(self, other):
        return self.position > other.position


def _guild(roles):
    by_id = {r.id: r for r in roles}
    return SimpleNamespace(
        id=1,
        roles=roles,
        get_role=lambda rid: by_id.get(rid),
        me=SimpleNamespace(
            top_role=FakeRole(900, 900, "bot_top"),
            guild_permissions=SimpleNamespace(manage_roles=True),
        ),
    )


def _interaction(guild, actor_top_role, is_admin=False):
    actor = SimpleNamespace(
        id=50,
        top_role=actor_top_role,
        guild_permissions=SimpleNamespace(administrator=is_admin, manage_roles=True),
    )
    return SimpleNamespace(
        guild=guild,
        user=actor,
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _run(coro):
    return asyncio.run(coro)


def _submit_schedule(interaction, user, date, add_roles=None, remove_roles=None):
    modal = ScheduleRoleModal(target_user=user)
    modal.roles_to_add.component._values = add_roles or []
    modal.roles_to_remove.component._values = remove_roles or []
    modal.date.component._value = date
    modal.time.component._value = ""
    modal.timezone_offset.component._value = ""
    return modal.on_submit(interaction)


def test_schedule_rejects_role_above_bots_hierarchy():
    too_high_role = FakeRole(1, 950, "too_high")  # above the bot's top_role (900)
    guild = _guild([too_high_role])
    actor_top = FakeRole(500, 500, "actor_top")
    interaction = _interaction(guild, actor_top)
    target_user = SimpleNamespace(id=60, mention="<@60>", display_name="Target")

    with patch.object(modals.db, "init_pool"), \
         patch.object(modals.db, "connection_pool", True), \
         patch.object(modals.db, "create_scheduled_role_change") as create_mock, \
         patch.object(modals, "send_error") as send_error_mock:
        _run(_submit_schedule(interaction, target_user, "2027-01-01", add_roles=[too_high_role]))

    create_mock.assert_not_called()
    send_error_mock.assert_awaited_once()
    assert "above my highest role" in send_error_mock.call_args[0][1]


def test_schedule_rejects_denied_role_for_add():
    role = FakeRole(1, 10, "deniable")
    guild = _guild([role])
    actor_top = FakeRole(500, 500, "actor_top")
    interaction = _interaction(guild, actor_top)
    target_user = SimpleNamespace(id=60, mention="<@60>", display_name="Target")

    with patch.object(modals.db, "init_pool"), \
         patch.object(modals.db, "connection_pool", True), \
         patch.object(modals.db, "is_role_denied", return_value=True), \
         patch.object(modals.db, "create_scheduled_role_change") as create_mock, \
         patch.object(modals, "send_error") as send_error_mock, \
         patch.object(modals, "record_role_deny_attempt", new=AsyncMock()) as deny_log:
        _run(_submit_schedule(interaction, target_user, "2027-01-01", add_roles=[role]))

    create_mock.assert_not_called()
    deny_log.assert_awaited_once()
    send_error_mock.assert_awaited_once()
    assert "denied" in send_error_mock.call_args[0][1]


def test_schedule_does_not_deny_check_removal_only_roles():
    # A role denied for being *granted* should not block *removing* it.
    role = FakeRole(1, 10, "deniable")
    guild = _guild([role])
    actor_top = FakeRole(500, 500, "actor_top")
    interaction = _interaction(guild, actor_top)
    target_user = SimpleNamespace(id=60, mention="<@60>", display_name="Target")

    with patch.object(modals.db, "init_pool"), \
         patch.object(modals.db, "connection_pool", True), \
         patch.object(modals.db, "is_role_denied", return_value=True) as deny_check, \
         patch.object(modals.db, "create_scheduled_role_change", return_value=123) as create_mock, \
         patch.object(modals, "send_error") as send_error_mock:
        _run(_submit_schedule(interaction, target_user, "2027-01-01", remove_roles=[role]))

    # is_role_denied should never even be consulted for a removal-only role.
    deny_check.assert_not_called()
    send_error_mock.assert_not_awaited()
    create_mock.assert_called_once()


def test_schedule_succeeds_when_checks_pass():
    role = FakeRole(1, 10, "ok_role")
    guild = _guild([role])
    actor_top = FakeRole(500, 500, "actor_top")
    interaction = _interaction(guild, actor_top)
    target_user = SimpleNamespace(id=60, mention="<@60>", display_name="Target")

    with patch.object(modals.db, "init_pool"), \
         patch.object(modals.db, "connection_pool", True), \
         patch.object(modals.db, "is_role_denied", return_value=False), \
         patch.object(modals.db, "create_scheduled_role_change", return_value=123) as create_mock, \
         patch.object(modals, "send_error") as send_error_mock:
        _run(_submit_schedule(interaction, target_user, "2027-01-01", add_roles=[role]))

    send_error_mock.assert_not_awaited()
    create_mock.assert_called_once()
    args = create_mock.call_args[0]
    assert args[0] == guild.id and args[1] == target_user.id and args[2] == [1]
