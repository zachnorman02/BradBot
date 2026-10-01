"""Unit tests for core.tasks.apply_scheduled_role_job -- the shared "apply
one due scheduled role change" helper used by both the periodic
scheduled_role_check sweep and counting's on-demand penalty-expiry check.

No pytest-asyncio dependency: each test just runs the coroutine directly
via asyncio.run(), same approach test_link_replacement_punctuation.py uses.
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.tasks as tasks


def _role(role_id):
    return SimpleNamespace(id=role_id)


def _guild(members=None, roles=None, fetch_member_result=None, fetch_member_raises=False):
    members = members or {}
    roles = roles or {}

    def get_member(user_id):
        return members.get(user_id)

    def get_role(role_id):
        return roles.get(role_id)

    async def fetch_member(user_id):
        if fetch_member_raises:
            raise Exception("not found")
        return fetch_member_result

    return SimpleNamespace(get_member=get_member, get_role=get_role, fetch_member=fetch_member)


def _member():
    return SimpleNamespace(add_roles=AsyncMock(), remove_roles=AsyncMock())


def _run(coro):
    return asyncio.run(coro)


def test_applies_add_and_remove_then_marks_completed():
    member = _member()
    add_role = _role(1)
    rem_role = _role(2)
    guild = _guild(members={42: member}, roles={1: add_role, 2: rem_role})
    job = {"id": 100, "user_id": 42, "add_ids": [1], "remove_ids": [2]}

    with patch.object(tasks.db, "mark_scheduled_role_status") as mark:
        _run(tasks.apply_scheduled_role_job(guild, job))

    member.add_roles.assert_awaited_once_with(add_role, reason="Scheduled role add")
    member.remove_roles.assert_awaited_once_with(rem_role, reason="Scheduled role remove")
    mark.assert_called_once_with(100, "completed", None)


def test_falls_back_to_fetch_member_when_not_cached():
    member = _member()
    guild = _guild(members={}, roles={}, fetch_member_result=member)
    job = {"id": 101, "user_id": 42, "add_ids": [], "remove_ids": []}

    with patch.object(tasks.db, "mark_scheduled_role_status") as mark:
        _run(tasks.apply_scheduled_role_job(guild, job))

    mark.assert_called_once_with(101, "completed", None)


def test_marks_failed_when_member_cannot_be_found():
    guild = _guild(members={}, roles={}, fetch_member_raises=True)
    job = {"id": 102, "user_id": 42, "add_ids": [], "remove_ids": []}

    with patch.object(tasks.db, "mark_scheduled_role_status") as mark:
        _run(tasks.apply_scheduled_role_job(guild, job))

    mark.assert_called_once_with(102, "failed", "User not found")


def test_marks_failed_and_skips_remove_when_add_roles_raises():
    member = _member()
    member.add_roles.side_effect = Exception("missing permissions")
    role = _role(1)
    guild = _guild(members={42: member}, roles={1: role})
    job = {"id": 103, "user_id": 42, "add_ids": [1], "remove_ids": [1]}

    with patch.object(tasks.db, "mark_scheduled_role_status") as mark:
        _run(tasks.apply_scheduled_role_job(guild, job))

    member.remove_roles.assert_not_awaited()
    mark.assert_called_once()
    args = mark.call_args[0]
    assert args[0] == 103 and args[1] == "failed" and "Add failed" in args[2]


def test_marks_failed_when_remove_roles_raises():
    member = _member()
    member.remove_roles.side_effect = Exception("missing permissions")
    role = _role(1)
    guild = _guild(members={42: member}, roles={1: role})
    job = {"id": 104, "user_id": 42, "add_ids": [], "remove_ids": [1]}

    with patch.object(tasks.db, "mark_scheduled_role_status") as mark:
        _run(tasks.apply_scheduled_role_job(guild, job))

    mark.assert_called_once()
    args = mark.call_args[0]
    assert args[0] == 104 and args[1] == "failed" and "Remove failed" in args[2]


def test_unresolvable_role_ids_are_skipped_without_error():
    member = _member()
    guild = _guild(members={42: member}, roles={})  # no roles registered -- all IDs unresolvable
    job = {"id": 105, "user_id": 42, "add_ids": [999], "remove_ids": [888]}

    with patch.object(tasks.db, "mark_scheduled_role_status") as mark:
        _run(tasks.apply_scheduled_role_job(guild, job))

    member.add_roles.assert_not_awaited()
    member.remove_roles.assert_not_awaited()
    mark.assert_called_once_with(105, "completed", None)
