"""Stateless unit-conversion slash commands."""
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
import aiohttp
from dateutil import parser

from utils.conversion_helpers import ConversionType, convert_testosterone
from commands.convert.helpers import convert_temperature, convert_length, convert_weight, convert_volume, convert_shoe_size
from commands.convert.choices import (
    TEMPERATURE_CHOICES, LENGTH_CHOICES, WEIGHT_CHOICES, VOLUME_CHOICES, SHOE_SYSTEM_CHOICES, SHOE_GENDER_CHOICES,
)


class ConversionGroup(app_commands.Group):
    """Slash commands under /convert."""

    def __init__(self):
        super().__init__(name="convert", description="Conversion utilities")

    @app_commands.command(name="testosterone", description="Convert testosterone dosages between gel and cypionate")
    @app_commands.describe(starting_type="Type of testosterone (cypionate or gel)", dose="Dose amount (in mg or ml)", frequency="Frequency of dose (in days)")
    @app_commands.choices(starting_type=[
        app_commands.Choice(name="Cypionate", value=ConversionType.CYPIONATE.value),
        app_commands.Choice(name="Gel", value=ConversionType.GEL.value),
    ])
    async def testosterone(self, interaction: discord.Interaction, starting_type: str, dose: float, frequency: int):
        response = convert_testosterone(starting_type, dose, frequency)
        await interaction.response.send_message(response)

    @app_commands.command(name="temperature", description="Convert temperatures between Celsius, Fahrenheit, or Kelvin")
    @app_commands.describe(value="Temperature value to convert", from_unit="Unit of the input value", to_unit="Unit to convert to")
    @app_commands.choices(from_unit=TEMPERATURE_CHOICES, to_unit=TEMPERATURE_CHOICES)
    async def temperature(self, interaction: discord.Interaction, value: float, from_unit: str, to_unit: str):
        try:
            result = convert_temperature(value, from_unit, to_unit)
            await interaction.response.send_message(f"🌡️ {value}°{from_unit.upper()} = {result:.2f}°{to_unit.upper()}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Temperature conversion failed: {e}", ephemeral=True)

    @app_commands.command(name="length", description="Convert between common length units (ft, m, km, miles, etc.)")
    @app_commands.describe(value="Distance to convert", from_unit="Unit of the input value", to_unit="Unit to convert to")
    @app_commands.choices(from_unit=LENGTH_CHOICES, to_unit=LENGTH_CHOICES)
    async def length(self, interaction: discord.Interaction, value: float, from_unit: str, to_unit: str):
        try:
            result = convert_length(value, from_unit, to_unit)
            await interaction.response.send_message(f"📏 {value} {from_unit} = {result:.4f} {to_unit}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Length conversion failed: {e}", ephemeral=True)

    @app_commands.command(name="weight", description="Convert between common weight units (kg, lb, oz, etc.)")
    @app_commands.describe(value="Weight to convert", from_unit="Unit of the input value", to_unit="Unit to convert to")
    @app_commands.choices(from_unit=WEIGHT_CHOICES, to_unit=WEIGHT_CHOICES)
    async def weight(self, interaction: discord.Interaction, value: float, from_unit: str, to_unit: str):
        try:
            result = convert_weight(value, from_unit, to_unit)
            await interaction.response.send_message(f"⚖️ {value} {from_unit} = {result:.4f} {to_unit}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Weight conversion failed: {e}", ephemeral=True)

    @app_commands.command(name="liquid", description="Convert between common liquid/volume units")
    @app_commands.describe(value="Volume to convert", from_unit="Unit of the input value", to_unit="Unit to convert to")
    @app_commands.choices(from_unit=VOLUME_CHOICES, to_unit=VOLUME_CHOICES)
    async def liquid(self, interaction: discord.Interaction, value: float, from_unit: str, to_unit: str):
        try:
            result = convert_volume(value, from_unit, to_unit)
            await interaction.response.send_message(f"🥤 {value} {from_unit} = {result:.4f} {to_unit}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Liquid conversion failed: {e}", ephemeral=True)

    @app_commands.command(name="currency", description="Convert currencies with live exchange rates")
    @app_commands.describe(amount="Amount to convert", from_currency="Three-letter code to convert from (e.g., USD)", to_currency="Three-letter code to convert to (e.g., EUR)")
    async def currency(self, interaction: discord.Interaction, amount: float, from_currency: str, to_currency: str):
        """Fetch real-time rate from open.er-api.com and convert the amount."""
        from_code, to_code = from_currency.upper(), to_currency.upper()

        if len(from_code) != 3 or len(to_code) != 3:
            await interaction.response.send_message("❌ Currency codes must be 3 letters (e.g., USD, EUR).", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        url = f"https://open.er-api.com/v6/latest/{from_code}"

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"❌ Rate lookup failed (HTTP {resp.status}).", ephemeral=True)
                        return
                    data = await resp.json()
        except Exception as e:
            await interaction.followup.send(f"❌ Error calling rate API: {e}", ephemeral=True)
            return

        if data.get("result") != "success":
            await interaction.followup.send(f"❌ Currency conversion failed: {data.get('error-type', 'Unknown error')}", ephemeral=True)
            return

        rate = data.get("rates", {}).get(to_code)
        if rate is None:
            await interaction.followup.send(f"❌ Could not find rate for {to_code}. Please check that both currency codes are valid.", ephemeral=True)
            return

        converted = amount * rate
        await interaction.followup.send(
            f"💱 {amount:.2f} {from_code} = {converted:.2f} {to_code}\nRate: {rate:.6f}\nUpdated: {data.get('time_last_update_utc', '')}",
            ephemeral=False,
        )

    @app_commands.command(name="timezone", description="Convert a date/time between timezones")
    @app_commands.describe(datetime_str="Date/time (e.g., '2024-01-05 15:30' or 'tomorrow 8pm')", from_timezone="Source timezone (e.g., UTC, America/New_York)", to_timezone="Target timezone (e.g., Europe/London)")
    async def timezone(self, interaction: discord.Interaction, datetime_str: str, from_timezone: str = "UTC", to_timezone: str = "UTC"):
        try:
            parsed = parser.parse(datetime_str)
            parsed = parsed.replace(tzinfo=ZoneInfo(from_timezone)) if parsed.tzinfo is None else parsed.astimezone(ZoneInfo(from_timezone))
            converted = parsed.astimezone(ZoneInfo(to_timezone))
            await interaction.response.send_message(
                f"🕒 **Time Conversion**\n`{parsed.strftime('%Y-%m-%d %H:%M:%S %Z')}` → `{converted.strftime('%Y-%m-%d %H:%M:%S %Z')}`"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Timezone conversion failed: {e}", ephemeral=True)

    @app_commands.command(name="shoe", description="Convert shoe sizes between various regions")
    @app_commands.describe(value="Shoe size value", from_system="Measurement system of the input size", to_system="Measurement system to convert to", from_gender="Men's or women's sizing for the input value", to_gender="Men's or women's sizing for the output value")
    @app_commands.choices(from_system=SHOE_SYSTEM_CHOICES, to_system=SHOE_SYSTEM_CHOICES, from_gender=SHOE_GENDER_CHOICES, to_gender=SHOE_GENDER_CHOICES)
    async def shoe(self, interaction: discord.Interaction, value: float, from_system: str, to_system: str, from_gender: str = "men", to_gender: str = "men"):
        try:
            result = convert_shoe_size(value, from_system, to_system, from_gender, to_gender)
            await interaction.response.send_message(
                f"👟 {from_gender.title()} size {value} ({from_system.upper()}) ≈ {result} ({to_gender.title()} {to_system.upper()})"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Shoe size conversion failed: {e}", ephemeral=True)
