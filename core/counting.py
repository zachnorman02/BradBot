"""
Counting channel handler: sequential counting with math expressions and penalties.
"""
import ast
import datetime as dt
import unicodedata
from typing import Optional

import discord

from database import db


ALLOWED_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow)
ALLOWED_UNARY_OPS = (ast.UAdd, ast.USub)


def _is_expression_safe(expr: str) -> bool:
    allowed_chars = set("0123456789+-*/()^ ")
    return all(ch in allowed_chars for ch in expr)


def _evaluate_expression(expr: str) -> Optional[int]:
    """
    Evaluate a simple arithmetic expression and return an integer result.
    Supports +, -, *, /, //, ^ (as exponent), parentheses, and unary +/-.
    Rejects floats and non-integer results.
    """
    expr = expr.strip()
    if not expr or len(expr) > 50:
        return None
    if not _is_expression_safe(expr):
        return None

    expr = expr.replace("^", "**")
    try:
        tree = ast.parse(expr, mode="eval")
    except Exception:
        return None

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                # Only allow integers (floats that are effectively int are ok)
                val = int(node.value)
                if val == node.value:
                    return val
            return None
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ALLOWED_UNARY_OPS):
            operand = _eval(node.operand)
            if operand is None:
                return None
            return operand if isinstance(node.op, ast.UAdd) else -operand
        if isinstance(node, ast.BinOp) and isinstance(node.op, ALLOWED_BIN_OPS):
            left = _eval(node.left)
            right = _eval(node.right)
            if left is None or right is None:
                return None
            # Guard against extremely large exponentiation
            if isinstance(node.op, ast.Pow):
                if abs(left) > 10_000 or abs(right) > 8:
                    return None
                result = left ** right
            elif isinstance(node.op, ast.Div):
                if right == 0:
                    return None
                result = left / right
                if not result.is_integer():
                    return None
                result = int(result)
            elif isinstance(node.op, ast.FloorDiv):
                if right == 0:
                    return None
                result = left // right
            elif isinstance(node.op, ast.Mult):
                if abs(left) > 10_000 or abs(right) > 10_000:
                    return None
                result = left * right
            elif isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            else:
                return None
            # Keep results within a sane range
            if abs(result) > 1_000_000_000:
                return None
            return result
        return None

    return _eval(tree)


def _normalize_digits(expr: str) -> str:
    """Convert any Unicode digit to its ASCII equivalent; leave other chars untouched."""
    # Add explicit mappings for numeral scripts that unicodedata.digit may not cover
    extra_map = {
        # Chinese/Japanese numerals
        "零": "0", "〇": "0",
        "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
        "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
    }
    normalized = []
    for ch in expr:
        if ch.isdigit():
            try:
                normalized.append(str(unicodedata.digit(ch)))
            except Exception:
                normalized.append(ch)
        elif ch in extra_map:
            normalized.append(extra_map[ch])
        else:
            normalized.append(ch)
    return "".join(normalized)


def _contains_non_ascii_digits(expr: str) -> bool:
    """Return True if the expression has any non-ASCII digit characters."""
    for ch in expr:
        if ch.isdigit() and ord(ch) > 127:
            return True
    return False


async def _apply_penalty(message: discord.Message, config: dict):
    """Assign the 'counting idiot' role and store expiry."""
    if not config.get("idiot_role_id"):
        return
    role = message.guild.get_role(config["idiot_role_id"])
    if not role:
        return

    expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=24)
    db.record_counting_penalty(message.guild.id, message.author.id, expires_at)

    if role not in message.author.roles:
        try:
            await message.author.add_roles(role, reason="Counting bot penalty (incorrect count)")
        except Exception as e:
            print(f"[COUNTING] Failed to add penalty role: {e}")


async def clear_counting_penalty_if_expired(guild: discord.Guild, member: discord.Member, expiry=None) -> bool:
    """Remove penalty role if expired. Returns True if cleared."""
    expiry = expiry or db.get_counting_penalty(guild.id, member.id)
    if not expiry:
        return False

    # Normalize expiry to aware datetime
    if isinstance(expiry, str):
        try:
            expiry = dt.datetime.fromisoformat(expiry)
        except Exception:
            return False
    now = dt.datetime.now(dt.timezone.utc)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=dt.timezone.utc)
    if expiry > now:
        return False

    config = db.get_counting_config(guild.id)
    if not config:
        return False

    role_id = config.get("idiot_role_id")
    if role_id:
        role = guild.get_role(role_id)
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason="Counting penalty expired")
            except Exception as e:
                print(f"[COUNTING] Failed to remove expired penalty role: {e}")
    db.clear_counting_penalty(guild.id, member.id)
    return True


async def _send_failure_message(message: discord.Message, reason: str):
    """Post a persistent failure reason in the channel."""
    try:
        await message.channel.send(
            f"{message.author.mention} broke the count: {reason}. Counter reset to **1**. Start over at 1!"
        )
    except Exception as e:
        print(f"[COUNTING] Failed to send failure message: {e}")


async def handle_counting_message(message: discord.Message):
    """Main entry for counting logic, called from on_message."""
    if not message.guild:
        return

    config = db.get_counting_config(message.guild.id)
    if not config:
        return

    # Enforce penalty expiry cleanup for the author (regardless of channel)
    await clear_counting_penalty_if_expired(message.guild, message.author)
    # If author still has penalty role but no DB record, remove it as stale
    try:
        role_id = config.get("idiot_role_id")
        if role_id:
            role = message.guild.get_role(role_id)
            if role and role in message.author.roles:
                if not db.get_counting_penalty(message.guild.id, message.author.id):
                    try:
                        await message.author.remove_roles(role, reason="Counting penalty stale (no DB record)")
                    except Exception as e:
                        print(f"[COUNTING] Failed to remove stale penalty role in on_message: {e}")
    except Exception:
        pass

    if message.channel.id != config["channel_id"]:
        return

    expected = config.get("next_number", 1)
    last_user_id = config.get("last_user_id")

    content = (message.content or "").strip()
    errors = []

    # Ignore pings/mentions or non-math chatter
    if not content:
        return
    if message.mention_everyone:
        return
    if message.role_mentions or message.raw_role_mentions:
        return
    # Block user mentions unless it's a reply
    if message.mentions:
        if not message.reference:
            return
        if len(message.mentions) > 1:
            return
    if "\n" in content:
        return
    normalized_content = _normalize_digits(content)
    if not _is_expression_safe(normalized_content):
        return

    value = _evaluate_expression(normalized_content)
    if value is None:
        errors.append("invalid or unsupported math expression (integers only)")
    else:
        if message.author.id == last_user_id and value != 1:
            errors.append("same user cannot go twice in a row")
        if value != expected:
            errors.append(f"expected **{expected}**")

    if not errors and value is not None and value == expected:
        # Advance counter
        db.update_counting_state(message.guild.id, expected + 1, message.author.id)
        try:
            await message.add_reaction("✅")
        except Exception:
            pass
        # If user used non-ASCII digits, echo the interpreted number for clarity
        if _contains_non_ascii_digits(content):
            try:
                await message.channel.send(
                    f"Number just sent: **{value}**."
                )
            except Exception as e:
                print(f"[COUNTING] Failed to send normalization info: {e}")
        return

    # Incorrect: reset to 1, clear last user so anyone can restart, and explain why
    try:
        await message.add_reaction("❌")
    except Exception:
        pass
    db.update_counting_state(message.guild.id, 1, None)
    await _apply_penalty(message, config)
    reason = "; ".join(errors) if errors else "wrong number"
    await _send_failure_message(message, reason)
