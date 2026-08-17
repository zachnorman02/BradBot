"""Modals for the booster-role domain.

BoosterCustomizeModal replaces the old separate `color`, `label`, and `icon`
slash commands with one form. It's shared by `/booster customize` (editing
your own role) and the admin "Edit Booster Role" user context menu (editing
someone else's), both of which resolve the target discord.Role before
opening the modal -- the modal itself only edits an existing role, it does
not create one.

Style is inferred from the hex/holographic fields (0/1 hex filled -> solid,
2 -> gradient, Holographic switched On -> holographic), which keeps the
form within Discord's 5-component-per-modal limit.

Holographic isn't a custom gradient -- Discord's API only recognizes one
exact tertiary-color triple as "holographic" (anything else 400s). So
"Holographic" is a real Off/On dropdown rather than a color field: turning
it On snaps the role to that fixed preset and ignores Primary/Secondary.
"""
import discord

from utils.color_parsing import parse_hex_color

# The one fixed RGB triple Discord's API treats as the "holographic" role
# style. Any other tertiary color combination is rejected by the API, so we
# don't attempt to honor whatever hex the user actually typed.
HOLOGRAPHIC_COLORS = (0xA9C9FF, 0xFFBBEC, 0xFFC3A0)


class BoosterCustomizeModal(discord.ui.Modal, title="Customize Booster Role"):
    role_name = discord.ui.Label(
        text="Role Name",
        description="Leave blank to keep the current name.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=100),
    )
    hex1 = discord.ui.Label(
        text="Primary Color",
        description="Hex like #FF0000. Blank = random (solid only).",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=7),
    )
    hex2 = discord.ui.Label(
        text="Secondary Color",
        description="Fill this too for a gradient.",
        component=discord.ui.TextInput(style=discord.TextStyle.short, required=False, max_length=7),
    )
    holographic = discord.ui.Label(
        text="Holographic",
        description="Discord fixes the shimmer colors -- turning this on ignores Primary/Secondary.",
        component=discord.ui.Select(
            options=[
                discord.SelectOption(label="Off", value="off", default=True),
                discord.SelectOption(label="On", value="on"),
            ],
            required=False,
        ),
    )
    icon = discord.ui.Label(
        text="Icon",
        description="Upload an image to set as the role icon (optional).",
        component=discord.ui.FileUpload(required=False, max_values=1),
    )

    def __init__(self, role: discord.Role, member: discord.Member):
        super().__init__()
        self.role = role
        self.member = member
        self.role_name.component.default = role.name

    async def on_submit(self, interaction: discord.Interaction):
        from commands.booster.helpers import save_role_to_db

        name = self.role_name.component.value.strip() or self.role.name

        hex1 = self.hex1.component.value.strip()
        hex2 = self.hex2.component.value.strip()
        want_holographic = "on" in self.holographic.component.values

        primary_color = self.role.color
        secondary_color = self.role.secondary_color
        tertiary_color = self.role.tertiary_color
        try:
            if want_holographic:
                primary_color, secondary_color, tertiary_color = (
                    discord.Color(c) for c in HOLOGRAPHIC_COLORS
                )
            elif hex2:
                primary_color = parse_hex_color(hex1, field_label="primary color") if hex1 else discord.Color.random()
                secondary_color = parse_hex_color(hex2, field_label="secondary color")
                tertiary_color = None
            elif hex1:
                primary_color = parse_hex_color(hex1, field_label="primary color")
                secondary_color = None
                tertiary_color = None
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
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
                edit_kwargs["display_icon"] = await icon_files[0].read()
            except discord.HTTPException as e:
                await interaction.response.send_message(f"❌ Could not read uploaded icon: {e}", ephemeral=True)
                return

        try:
            await self.role.edit(**edit_kwargs)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to edit that role.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Discord error: {e}", ephemeral=True)
            return

        await save_role_to_db(self.member.id, self.role.guild.id, self.role)
        note = " (Primary/Secondary ignored -- Holographic was On)" if want_holographic and (hex1 or hex2) else ""
        await interaction.response.send_message(
            f"✅ Updated {self.member.mention}'s booster role: {self.role.mention}{note}", ephemeral=True
        )
