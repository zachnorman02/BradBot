# Code Review Checklist

Use this checklist when adding new features or reviewing code.

## ✅ General Code Quality

- [ ] No unused imports
- [ ] Imports organized: standard lib → third-party → local
- [ ] Functions have docstrings
- [ ] Type hints on all function parameters and returns
- [ ] No magic numbers or strings (use `config.py`)
- [ ] Descriptive variable names

## ✅ Logging

- [ ] No `print()` statements (use `logger` instead)
- [ ] Errors logged with `logger.error()`
- [ ] Warnings logged with `logger.warning()`
- [ ] Info logged with `logger.info()`
- [ ] Debug info logged with `logger.debug()`

## ✅ Discord Interactions

- [ ] Use `require_guild()` for guild-only commands
- [ ] Use `send_error()` for errors
- [ ] Use `send_success()` for success messages
- [ ] Use `send_warning()` for warnings
- [ ] Use `send_info()` for informational messages
- [ ] Check `interaction.response.is_done()` before sending

## ✅ Database Operations

- [ ] Use config constants for setting keys
- [ ] Use config constants for default values
- [ ] Proper error handling with try/except
- [ ] Connection errors logged appropriately
- [ ] Queries use parameterized statements (no SQL injection)

## ✅ Error Handling

- [ ] All exceptions caught appropriately
- [ ] User-friendly error messages
- [ ] Errors logged for debugging
- [ ] No bare `except:` clauses
- [ ] Specific exception types caught

## ✅ Code Organization

- [ ] Functions < 50 lines
- [ ] Files < 500 lines (consider splitting)
- [ ] Related functions grouped together
- [ ] Clear section comments
- [ ] No duplicate code (extract to helper)

## ✅ Discord Best Practices

- [ ] Ephemeral messages for errors
- [ ] Public messages for successes (unless sensitive)
- [ ] Commands have clear descriptions
- [ ] Parameters have descriptions
- [ ] Permission checks where needed
- [ ] Rate limiting considered

## ✅ Testing Considerations

- [ ] Edge cases handled
- [ ] Invalid input handled gracefully
- [ ] Null/None checks where needed
- [ ] Permission denied handled
- [ ] Network errors handled

## ✅ Performance

- [ ] No N+1 query problems
- [ ] Database connections closed properly
- [ ] Large lists paginated
- [ ] Caching used where appropriate
- [ ] Async/await used correctly

## ✅ Documentation

- [ ] Command documented in `/docs/commands.md`
- [ ] Config values documented in `config.py`
- [ ] Complex logic has comments
- [ ] Public functions have docstrings
- [ ] README updated if needed

## Example Review

### ❌ Bad
```python
@app_commands.command()
async def cmd(interaction, x):
    if not interaction.guild:
        await interaction.response.send_message("error", ephemeral=True)
        return
    val = db.get_guild_setting(interaction.guild.id, 'setting', 'false')
    if val == 'true':
        print("doing thing")
        await interaction.response.send_message("ok")
```

### ✅ Good
```python
from config import SETTING_FEATURE_NAME, DEFAULT_FALSE
from utils import logger, send_success, require_guild

@app_commands.command(name="cmd", description="Clear description of what this does")
@app_commands.describe(x="Description of parameter x")
async def cmd(interaction: discord.Interaction, x: str) -> None:
    """
    Full docstring explaining what this command does.
    
    Args:
        interaction: Discord interaction
        x: Parameter description
    """
    if not await require_guild(interaction):
        return
    
    setting_value = db.get_guild_setting(
        interaction.guild.id,
        SETTING_FEATURE_NAME,
        DEFAULT_FALSE
    )
    
    if setting_value.lower() == 'true':
        logger.info(f"Executing feature for guild {interaction.guild.id}")
        await send_success(interaction, "Operation completed successfully")
```

## Notes

- Not every rule applies to every situation
- Use common sense
- When in doubt, prioritize readability
- Consistency > perfection
