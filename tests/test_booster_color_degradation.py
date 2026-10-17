"""Unit tests for the ENHANCED_ROLE_COLORS degrade/reconcile fix:
_degraded_colors_for_guild (commands/booster/helpers.py) and
_reconcile_degraded_booster_colors (core/tasks.py). Before this fix, a
guild missing ENHANCED_ROLE_COLORS (e.g. a boost-level drop) made the
*entire* role create/restore 400 and fail -- a booster got no role at all
on reboost instead of just losing their gradient.

No pytest-asyncio dependency: asyncio.run() per test, same pattern as the
rest of this suite.
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord

import commands.booster.helpers as booster_helpers
import core.tasks as tasks
from commands.booster.helpers import _degraded_colors_for_guild


def _run(coro):
    return asyncio.run(coro)


def _guild(features):
    return SimpleNamespace(id=1, name="g", features=features)


def test_degraded_colors_passthrough_when_feature_present():
    guild = _guild(["ENHANCED_ROLE_COLORS"])
    secondary = discord.Color(0x00FF00)
    tertiary = discord.Color(0x0000FF)
    assert _degraded_colors_for_guild(guild, secondary, tertiary) == (secondary, tertiary)


def test_degraded_colors_noop_when_nothing_to_degrade():
    """A plain solid-color role (no secondary/tertiary) shouldn't trigger
    the degrade path (or its log line) even without the feature."""
    guild = _guild([])
    assert _degraded_colors_for_guild(guild, None, None) == (None, None)


def test_degraded_colors_drops_secondary_without_feature():
    guild = _guild([])
    secondary = discord.Color(0x00FF00)
    assert _degraded_colors_for_guild(guild, secondary, None) == (None, None)


def test_degraded_colors_drops_tertiary_without_feature():
    """Holographic roles only set tertiary_color -- same degrade applies."""
    guild = _guild([])
    tertiary = discord.Color(0x0000FF)
    assert _degraded_colors_for_guild(guild, None, tertiary) == (None, None)


def _role(role_id, secondary_color=None, tertiary_color=None, edit=None):
    return SimpleNamespace(
        id=role_id, name=f"role{role_id}", secondary_color=secondary_color, tertiary_color=tertiary_color,
        edit=edit or AsyncMock(),
    )


def _booster_row(role_id, secondary_hex=None, tertiary_hex=None):
    return {'role_id': role_id, 'secondary_color_hex': secondary_hex, 'tertiary_color_hex': tertiary_hex}


def test_reconcile_skips_entirely_when_feature_still_missing():
    guild = _guild([])  # no ENHANCED_ROLE_COLORS
    with patch.object(tasks.db, "get_all_booster_roles") as get_mock:
        _run(tasks._reconcile_degraded_booster_colors(guild))
    get_mock.assert_not_called()  # short-circuits before even querying the DB


def test_reconcile_skips_rows_with_no_saved_gradient():
    guild = _guild(["ENHANCED_ROLE_COLORS"])
    with patch.object(tasks.db, "get_all_booster_roles", return_value=[_booster_row(10)]):
        guild.get_role = lambda rid: (_ for _ in ()).throw(AssertionError("should never look up a plain solid role"))
        _run(tasks._reconcile_degraded_booster_colors(guild))


def test_reconcile_skips_when_role_missing():
    guild = _guild(["ENHANCED_ROLE_COLORS"])
    guild.get_role = lambda rid: None
    with patch.object(tasks.db, "get_all_booster_roles", return_value=[_booster_row(10, secondary_hex="#00ff00")]):
        _run(tasks._reconcile_degraded_booster_colors(guild))  # just shouldn't raise


def test_reconcile_skips_when_already_matching():
    secondary = discord.Color(0x00FF00)
    role = _role(10, secondary_color=secondary)
    guild = _guild(["ENHANCED_ROLE_COLORS"])
    guild.get_role = lambda rid: role
    with patch.object(tasks.db, "get_all_booster_roles", return_value=[_booster_row(10, secondary_hex="#00ff00")]):
        _run(tasks._reconcile_degraded_booster_colors(guild))
    role.edit.assert_not_awaited()


def test_reconcile_reapplies_degraded_gradient():
    role = _role(10, secondary_color=None, tertiary_color=None)  # currently degraded to solid
    guild = _guild(["ENHANCED_ROLE_COLORS"])
    guild.get_role = lambda rid: role
    with patch.object(tasks.db, "get_all_booster_roles", return_value=[_booster_row(10, secondary_hex="#00ff00")]), \
         patch.object(tasks.asyncio, "sleep", new=AsyncMock()):
        _run(tasks._reconcile_degraded_booster_colors(guild))

    role.edit.assert_awaited_once()
    kwargs = role.edit.call_args.kwargs
    assert kwargs["secondary_color"] == discord.Color(0x00FF00)
    assert kwargs["tertiary_color"] is None


def test_reconcile_reapplies_degraded_holographic():
    role = _role(10)  # currently degraded to solid
    guild = _guild(["ENHANCED_ROLE_COLORS"])
    guild.get_role = lambda rid: role
    with patch.object(tasks.db, "get_all_booster_roles", return_value=[_booster_row(10, tertiary_hex="#0000ff")]), \
         patch.object(tasks.asyncio, "sleep", new=AsyncMock()):
        _run(tasks._reconcile_degraded_booster_colors(guild))

    role.edit.assert_awaited_once()
    assert role.edit.call_args.kwargs["tertiary_color"] == discord.Color(0x0000FF)


def test_save_role_to_db_defaults_to_live_role_colors():
    """Backward-compatible default: every existing caller that doesn't pass
    overrides keeps reading straight off the live role."""
    role = SimpleNamespace(
        color=discord.Color(0xFF0000), secondary_color=discord.Color(0x00FF00), tertiary_color=None,
        icon=None, id=1, name="role",
    )
    with patch.object(booster_helpers.db, "store_booster_role") as store_mock:
        _run(booster_helpers.save_role_to_db(1, 2, role))
    assert store_mock.call_args.kwargs["secondary_color_hex"] == "#00ff00"
    assert store_mock.call_args.kwargs["color_type"] == "gradient"


def test_save_role_to_db_override_preserves_degraded_request():
    """When the live role was degraded to solid-only, passing the member's
    originally-requested colors explicitly saves those instead of the
    (now color-less) live role -- the whole point of the override."""
    role = SimpleNamespace(
        color=discord.Color(0xFF0000), secondary_color=None, tertiary_color=None,
        icon=None, id=1, name="role",
    )
    requested_secondary = discord.Color(0x00FF00)
    with patch.object(booster_helpers.db, "store_booster_role") as store_mock:
        _run(booster_helpers.save_role_to_db(1, 2, role, secondary_color=requested_secondary, tertiary_color=None))
    assert store_mock.call_args.kwargs["secondary_color_hex"] == "#00ff00"
    assert store_mock.call_args.kwargs["color_type"] == "gradient"


def test_on_guild_update_reconciles_when_feature_newly_available():
    before = _guild([])
    after = _guild(["ENHANCED_ROLE_COLORS"])
    after.id, after.name = 1, "g"
    with patch.object(tasks.db, "get_guild_setting", return_value="true"), \
         patch.object(tasks, "_reconcile_degraded_booster_colors", new=AsyncMock()) as reconcile_mock:
        _run(tasks.on_guild_update_handler(before, after))
    reconcile_mock.assert_awaited_once_with(after)


def test_on_guild_update_ignores_unrelated_feature_changes():
    before = _guild(["SOME_OTHER_FEATURE"])
    after = _guild(["SOME_OTHER_FEATURE", "ANOTHER_ONE"])
    with patch.object(tasks, "_reconcile_degraded_booster_colors", new=AsyncMock()) as reconcile_mock:
        _run(tasks.on_guild_update_handler(before, after))
    reconcile_mock.assert_not_called()


def test_on_guild_update_respects_booster_roles_disabled():
    before = _guild([])
    after = _guild(["ENHANCED_ROLE_COLORS"])
    after.id, after.name = 1, "g"
    with patch.object(tasks.db, "get_guild_setting", return_value="false"), \
         patch.object(tasks, "_reconcile_degraded_booster_colors", new=AsyncMock()) as reconcile_mock:
        _run(tasks.on_guild_update_handler(before, after))
    reconcile_mock.assert_not_called()
