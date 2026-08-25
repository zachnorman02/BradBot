"""Unit tests for utils.role_parsing (no live Discord connection needed)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.role_parsing import parse_role_list, format_role_list


class FakeRole:
    def __init__(self, id_, name):
        self.id = id_
        self.name = name

    @property
    def mention(self):
        return f"<@&{self.id}>"


class FakeGuild:
    def __init__(self, roles):
        self.roles = roles

    def get_role(self, role_id):
        return next((r for r in self.roles if r.id == role_id), None)


def _guild():
    return FakeGuild([
        FakeRole(111, "Verified"),
        FakeRole(222, "Booster"),
        FakeRole(333, "Muted"),
    ])


def test_parse_role_list_by_mention():
    guild = _guild()
    resolved, unresolved = parse_role_list(guild, "<@&111>, <@&222>")
    assert [r.id for r in resolved] == [111, 222]
    assert unresolved == []


def test_parse_role_list_by_id_and_name():
    guild = _guild()
    resolved, unresolved = parse_role_list(guild, "111, Booster")
    assert [r.id for r in resolved] == [111, 222]
    assert unresolved == []


def test_parse_role_list_unresolved_token():
    guild = _guild()
    resolved, unresolved = parse_role_list(guild, "Verified, NotARole")
    assert [r.id for r in resolved] == [111]
    assert unresolved == ["NotARole"]


def test_parse_role_list_empty_string():
    guild = _guild()
    resolved, unresolved = parse_role_list(guild, "")
    assert resolved == []
    assert unresolved == []


def test_format_role_list_roundtrip():
    guild = _guild()
    resolved, _ = parse_role_list(guild, "Verified, Booster")
    assert format_role_list(resolved) == "<@&111>, <@&222>"
