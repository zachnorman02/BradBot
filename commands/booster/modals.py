"""Modals for the booster-role domain.

BoosterCustomizeModal replaces the old separate `color`, `label`, and `icon`
slash commands with one form. It's shared by `/booster customize` (editing
your own role) and the admin "Edit Booster Role" user context menu (editing
someone else's), both of which resolve the target discord.Role before
opening the modal -- the modal itself only edits an existing role, it does
not create one.

Discord caps modals at 5 top-level components, which forced two design
choices here:

- Primary/Secondary share one "Colors" field ('#FF0000' for solid,
  '#FF0000,#00FF00' for a gradient) instead of one field each, freeing a
  slot for Clear Icon. Each side is independently keep/clear/set: blank
  keeps that color, the literal text "clear" resets it, anything else is
  parsed as hex.
- Holographic isn't a custom gradient -- Discord's API only recognizes one
  exact tertiary-color triple as "holographic" (anything else 400s). So
  it's a real Off/On dropdown rather than a color field, preselected to
  match the role's current state so leaving it alone never changes it.
  Turning it On ignores the Colors field entirely.
- Icon upload can't itself signal "remove" (there's no way to submit an
  empty file, and modals can't pre-show "here's your current icon" to
  react to), so Clear Icon is a separate Off/On dropdown. Uploading a new
  icon always wins over Clear Icon if both are set.
"""
import asyncio

import discord

from utils.color_parsing import parse_hex_color
from utils.image_processing import prepare_role_icon

# The one fixed RGB triple Discord's API treats as the "holographic" role
# style. Any other tertiary color combination is rejected by the API, so we
# don't attempt to honor whatever hex the user actually typed.
HOLOGRAPHIC_COLORS = (0xA9C9FF, 0xFFBBEC, 0xFFC3A0)

CLEAR_TOKEN = "clear"


def _resolve_color_field(raw: str, *, field_label: str):
    """Returns ('keep' | 'clear' | 'set', discord.Color | None)."""
    if not raw:
        return "keep", None
    if raw.lower() == CLEAR_TOKEN:
        return "clear", None
    return "set", parse_hex_color(raw, field_label=field_label)


def _resolve_colors_field(raw: str):
    """Parse the merged Primary/Secondary "Colors" field.

    No comma means the whole value applies to Primary and Secondary is
    forced to clear, matching the old "fill in one field" = solid
    behavior. With a comma, each side is resolved independently.

    Returns (primary_action, primary_value, secondary_action, secondary_value).
    """
    raw = raw.strip()
    if not raw:
        return "keep", None, "keep", None
    if "," in raw:
        left, right = raw.split(",", 1)
        p_action, p_value = _resolve_color_field(left.strip(), field_label="primary color")
        s_action, s_value = _resolve_color_field(right.strip(), field_label="secondary color")
        return p_action, p_value, s_action, s_value
    p_action, p_value = _resolve_color_field(raw, field_label="primary color")
    return p_action, p_value, "clear", None


class BoosterCustomizeModal(discord.ui.Modal, title="Customize Booster Role"):
    role_name = discord.ui.Label(
        text="Role Name",
        description="Leave blank to keep the current name.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=100),
    )
    colors = discord.ui.Label(
        text="Colors",
        description="'#FF0000' = solid, '#FF0000,#00FF00' = gradient. Blank = keep current. 'clear' = reset.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=20),
    )
    holographic = discord.ui.Label(
        text="Holographic",
        description="Discord fixes the shimmer colors -- turning this on ignores Colors.",
        component=discord.ui.Select(
            options=[
                discord.SelectOption(label="Off", value="off"),
                discord.SelectOption(label="On", value="on"),
            ],
            required=False,
        ),
    )
    icon = discord.ui.Label(
        text="Icon",
        description="Upload an image to set as the role icon. Blank = keep current.",
        component=discord.ui.FileUpload(required=False, max_values=1),
    )
    clear_icon = discord.ui.Label(
        text="Clear Icon",
        description="On = remove the icon entirely (ignored if you also upload one above).",
        component=discord.ui.Select(
            options=[
                discord.SelectOption(label="Off", value="off", default=True),
                discord.SelectOption(label="On", value="on"),
            ],
            required=False,
        ),
    )

    def __init__(self, role: discord.Role, member: discord.Member):
        super().__init__()
        self.role = role
        self.member = member
        self.role_name.component.default = role.name
        if role.color.value:
            prefill = f"#{role.color.value:06X}"
            if role.secondary_color:
                prefill += f",#{role.secondary_color.value:06X}"
            self.colors.component.default = prefill
        is_holographic_now = role.tertiary_color is not None
        self.holographic.component.options[0].default = not is_holographic_now
        self.holographic.component.options[1].default = is_holographic_now

    async def on_submit(self, interaction: discord.Interaction):
        from commands.booster.helpers import save_role_to_db

        # Icon processing + the role edit can take longer than Discord's ~3s
        # ack window (a large valid upload alone can take a moment to decode
        # and quantize), so acknowledge immediately and respond via followup
        # for every path below instead of the initial interaction response.
        await interaction.response.defer(ephemeral=True)

        name = self.role_name.component.value.strip() or self.role.name

        colors_raw = self.colors.component.value.strip()
        want_holographic = "on" in self.holographic.component.values
        want_clear_icon = "on" in self.clear_icon.component.values

        primary_color = self.role.color
        secondary_color = self.role.secondary_color
        tertiary_color = self.role.tertiary_color
        try:
            if want_holographic:
                primary_color, secondary_color, tertiary_color = (
                    discord.Color(c) for c in HOLOGRAPHIC_COLORS
                )
            else:
                tertiary_color = None  # holographic explicitly off

                p_action, p_value, s_action, s_value = _resolve_colors_field(colors_raw)
                if p_action == "clear":
                    primary_color = discord.Color.random()
                elif p_action == "set":
                    primary_color = p_value

                if s_action == "clear":
                    secondary_color = None
                elif s_action == "set":
                    secondary_color = s_value
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return

        icon_files = self.icon.component.values
        edit_kwargs = dict(
            name=name,
            color=primary_color,
            secondary_color=secondary_color,
            tertiary_color=tertiary_color,
            reason=f"Booster role customized by {interaction.user}",
        )
        if icon_files:
            try:
                icon_bytes = await icon_files[0].read()
            except discord.HTTPException as e:
                await interaction.followup.send(f"❌ Could not read uploaded icon: {e}", ephemeral=True)
                return
            # Decoding/quantizing/re-encoding is CPU-bound; keep it off the event loop.
            edit_kwargs["display_icon"] = await asyncio.to_thread(prepare_role_icon, icon_bytes)
        elif want_clear_icon:
            edit_kwargs["display_icon"] = None

        try:
            await self.role.edit(**edit_kwargs)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to edit that role.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Discord error: {e}", ephemeral=True)
            return

        await save_role_to_db(self.member.id, self.role.guild.id, self.role)
        note = " (Colors ignored -- Holographic was On)" if want_holographic and colors_raw else ""
        await interaction.followup.send(
            f"✅ Updated {self.member.mention}'s booster role: {self.role.mention}{note}", ephemeral=True
        )
