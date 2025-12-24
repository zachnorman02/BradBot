"""
Counting channel handler: sequential counting with math expressions and penalties.
"""
import ast
import datetime as dt
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


async def _clear_expired_penalty(message: discord.Message, config: dict):
    """Remove penalty role if expired."""
    expiry = db.get_counting_penalty(message.guild.id, message.author.id)
    if not expiry:
        return
    now = dt.datetime.now(dt.timezone.utc)
    if expiry > now:
        return

    role_id = config.get("idiot_role_id")
    if role_id:
        role = message.guild.get_role(role_id)
        if role and role in message.author.roles:
            try:
                await message.author.remove_roles(role, reason="Counting penalty expired")
            except Exception as e:
                print(f"[COUNTING] Failed to remove expired penalty role: {e}")
    db.clear_counting_penalty(message.guild.id, message.author.id)


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

    if message.channel.id != config["channel_id"]:
        return

    # Enforce penalty expiry cleanup for the author
    await _clear_expired_penalty(message, config)

    expected = config.get("next_number", 1)
    last_user_id = config.get("last_user_id")

    content = (message.content or "").strip()
    errors = []
    if "\n" in content or not content:
        errors.append("must be a single-line number/expression")

    value = _evaluate_expression(content)
    if value is None:
        errors.append("invalid or unsupported math expression (integers only)")
    else:
        if value != expected:
            errors.append(f"expected **{expected}**")
        if message.author.id == last_user_id and value != 1:
            errors.append("same user cannot go twice in a row")

    if not errors and value is not None and value == expected:
        # Advance counter
        db.update_counting_state(message.guild.id, expected + 1, message.author.id)
        try:
            await message.add_reaction("✅")
        except Exception:
            pass
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
