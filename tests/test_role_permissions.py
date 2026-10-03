"""Unit tests for utils.role_permissions (no live Discord connection needed)."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.role_permissions import check_role_hierarchy, check_role_action_allowed


class FakeRole:
    def __init__(self, position, managed=False, default=False, name="Role"):
        self.position = position
        self.managed = managed
        self.name = name
        self.mention = f"@{name}"
        self.id = position
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


def _member(top_role, manage_roles=True, administrator=False):
    return SimpleNamespace(top_role=top_role, guild_permissions=SimpleNamespace(manage_roles=manage_roles, administrator=administrator))


def test_cannot_manage_everyone_role():
    everyone = FakeRole(0, default=True)
    actor = _member(FakeRole(10))
    bot = _member(FakeRole(10))
    assert check_role_hierarchy(actor, bot, everyone) == "You can't manage @everyone."


def test_cannot_manage_managed_role():
    role = FakeRole(5, managed=True)
    actor = _member(FakeRole(10))
    bot = _member(FakeRole(10))
    error = check_role_hierarchy(actor, bot, role)
    assert error is not None and "managed by an integration" in error


def test_bot_missing_manage_roles_permission():
    role = FakeRole(5)
    actor = _member(FakeRole(10))
    bot = _member(FakeRole(10), manage_roles=False)
    error = check_role_hierarchy(actor, bot, role)
    assert error == "I need the Manage Roles permission to do that."


def test_role_above_bots_top_role_is_rejected():
    role = FakeRole(10)
    actor = _member(FakeRole(20))
    bot = _member(FakeRole(5))  # bot's top role (position 5) is below the target role (10)
    error = check_role_hierarchy(actor, bot, role)
    assert error is not None and "above my highest role" in error


def test_role_at_or_above_actors_top_role_is_rejected():
    role = FakeRole(10)
    actor = _member(FakeRole(10))  # actor's top role is equal to the target role
    bot = _member(FakeRole(20))
    error = check_role_hierarchy(actor, bot, role)
    assert error is not None and "higher than or equal to your top role" in error


def test_administrator_bypasses_actor_hierarchy_check():
    role = FakeRole(10)
    actor = _member(FakeRole(5), administrator=True)  # below the role, but is an admin
    bot = _member(FakeRole(20))
    assert check_role_hierarchy(actor, bot, role) is None


def test_fully_permitted_change_returns_none():
    role = FakeRole(5)
    actor = _member(FakeRole(10))
    bot = _member(FakeRole(20))
    assert check_role_hierarchy(actor, bot, role) is None


def test_check_role_action_allowed_denied():
    role = FakeRole(5, name="Blocked")
    error = check_role_action_allowed(123, role, is_denied=lambda guild_id, role_id: True)
    assert error is not None and "restricted" in error


def test_check_role_action_allowed_not_denied():
    role = FakeRole(5)
    assert check_role_action_allowed(123, role, is_denied=lambda guild_id, role_id: False) is None
