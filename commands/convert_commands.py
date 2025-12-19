"""
Conversion command group (/convert …)
"""
import datetime as dt
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from dateutil import parser

from utils.conversion_helpers import ConversionType, convert_testosterone


def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    from_unit = from_unit.lower()
    to_unit = to_unit.lower()
    if from_unit == to_unit:
        return value

    if from_unit == "c":
        celsius = value
    elif from_unit == "f":
        celsius = (value - 32) * 5 / 9
    elif from_unit == "k":
        celsius = value - 273.15
    else:
        raise ValueError("Unsupported temperature unit")

    if to_unit == "c":
        return celsius
    if to_unit == "f":
        return (celsius * 9 / 5) + 32
    if to_unit == "k":
        return celsius + 273.15
    raise ValueError("Unsupported temperature unit")


LENGTH_TO_METERS = {
    "m": 1.0,
    "km": 1000.0,
    "cm": 0.01,
    "mm": 0.001,
    "mi": 1609.34,
    "ft": 0.3048,
    "in": 0.0254,
    "yd": 0.9144,
}


def _convert_length(value: float, from_unit: str, to_unit: str) -> float:
    from_unit = from_unit.lower()
    to_unit = to_unit.lower()
    if from_unit not in LENGTH_TO_METERS or to_unit not in LENGTH_TO_METERS:
        raise ValueError("Unsupported length unit")
    meters = value * LENGTH_TO_METERS[from_unit]
    return meters / LENGTH_TO_METERS[to_unit]


WEIGHT_TO_KG = {
    "kg": 1.0,
    "g": 0.001,
    "mg": 0.000001,
    "lb": 0.453592,
    "oz": 0.0283495,
    "stone": 6.35029,
}


def _convert_weight(value: float, from_unit: str, to_unit: str) -> float:
    from_unit = from_unit.lower()
    to_unit = to_unit.lower()
    if from_unit not in WEIGHT_TO_KG or to_unit not in WEIGHT_TO_KG:
        raise ValueError("Unsupported weight unit")
    kilograms = value * WEIGHT_TO_KG[from_unit]
    return kilograms / WEIGHT_TO_KG[to_unit]


def _convert_shoe_size(value: float, from_system: str, to_system: str, gender: str) -> float:
    """
    Approximate shoe size conversion using simple offsets.
    Supported systems: us, uk, eu, cm
    Gender: men, women
    """
    from_system = from_system.lower()
    to_system = to_system.lower()
    gender = gender.lower()
    if gender not in ("men", "women"):
        raise ValueError("Gender must be 'men' or 'women'")

    # convert to centimeters using Brannock approximations
    if from_system == "cm":
        cm = value
    elif from_system == "us":
        cm = (value + (23 if gender == "men" else 22)) * 0.667
    elif from_system == "uk":
        cm = (value + 23.5) * 0.667
    elif from_system == "eu":
        cm = value / 1.5
    else:
        raise ValueError("Unsupported shoe size system")

    if to_system == "cm":
        return round(cm, 2)
    if to_system == "us":
        return round(((cm / 0.667) - (23 if gender == "men" else 22)), 1)
    if to_system == "uk":
        return round(((cm / 0.667) - 23.5), 1)
    if to_system == "eu":
        return round(cm * 1.5, 1)
    raise ValueError("Unsupported shoe size system")


class ConversionGroup(app_commands.Group):
    """Slash commands under /convert"""

    def __init__(self):
        super().__init__(name="convert", description="Conversion utilities")

    @app_commands.command(name="testosterone", description="Convert testosterone dosages between gel and cypionate")
    @app_commands.describe(
        starting_type="Type of testosterone (cypionate or gel)",
        dose="Dose amount (in mg or ml)",
        frequency="Frequency of dose (in days)"
    )
    @app_commands.choices(starting_type=[
        app_commands.Choice(name="Cypionate", value=ConversionType.CYPIONATE.value),
        app_commands.Choice(name="Gel", value=ConversionType.GEL.value)
    ])
    async def testosterone(
        self,
        interaction: discord.Interaction,
        starting_type: str,
        dose: float,
        frequency: int
    ):
        """Conversion helper forwarding to the legacy calculator."""
        response = convert_testosterone(starting_type, dose, frequency)
        await interaction.response.send_message(response)

    @app_commands.command(name="temperature", description="Convert temperatures between Celsius, Fahrenheit, or Kelvin")
    @app_commands.describe(
        value="Temperature value to convert",
        from_unit="Unit of the input value",
        to_unit="Unit to convert to"
    )
    @app_commands.choices(from_unit=[
        app_commands.Choice(name="Celsius (°C)", value="c"),
        app_commands.Choice(name="Fahrenheit (°F)", value="f"),
        app_commands.Choice(name="Kelvin (K)", value="k"),
    ], to_unit=[
        app_commands.Choice(name="Celsius (°C)", value="c"),
        app_commands.Choice(name="Fahrenheit (°F)", value="f"),
        app_commands.Choice(name="Kelvin (K)", value="k"),
    ])
    async def temperature(self, interaction: discord.Interaction, value: float, from_unit: str, to_unit: str):
        try:
            result = _convert_temperature(value, from_unit, to_unit)
            await interaction.response.send_message(f"🌡️ {value}°{from_unit.upper()} = {result:.2f}°{to_unit.upper()}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Temperature conversion failed: {e}", ephemeral=True)

    @app_commands.command(name="length", description="Convert between common length units (ft, m, km, miles, etc.)")
    @app_commands.describe(
        value="Distance to convert",
        from_unit="Unit of the input value",
        to_unit="Unit to convert to"
    )
    @app_commands.choices(from_unit=[
        app_commands.Choice(name="Meters (m)", value="m"),
        app_commands.Choice(name="Kilometers (km)", value="km"),
        app_commands.Choice(name="Centimeters (cm)", value="cm"),
        app_commands.Choice(name="Millimeters (mm)", value="mm"),
        app_commands.Choice(name="Miles (mi)", value="mi"),
        app_commands.Choice(name="Feet (ft)", value="ft"),
        app_commands.Choice(name="Inches (in)", value="in"),
        app_commands.Choice(name="Yards (yd)", value="yd"),
    ], to_unit=[
        app_commands.Choice(name="Meters (m)", value="m"),
        app_commands.Choice(name="Kilometers (km)", value="km"),
        app_commands.Choice(name="Centimeters (cm)", value="cm"),
        app_commands.Choice(name="Millimeters (mm)", value="mm"),
        app_commands.Choice(name="Miles (mi)", value="mi"),
        app_commands.Choice(name="Feet (ft)", value="ft"),
        app_commands.Choice(name="Inches (in)", value="in"),
        app_commands.Choice(name="Yards (yd)", value="yd"),
    ])
    async def length(self, interaction: discord.Interaction, value: float, from_unit: str, to_unit: str):
        try:
            result = _convert_length(value, from_unit, to_unit)
            await interaction.response.send_message(f"📏 {value} {from_unit} = {result:.4f} {to_unit}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Length conversion failed: {e}", ephemeral=True)

    @app_commands.command(name="weight", description="Convert between common weight units (kg, lb, oz, etc.)")
    @app_commands.describe(
        value="Weight to convert",
        from_unit="Unit of the input value",
        to_unit="Unit to convert to"
    )
    @app_commands.choices(from_unit=[
        app_commands.Choice(name="Kilograms (kg)", value="kg"),
        app_commands.Choice(name="Grams (g)", value="g"),
        app_commands.Choice(name="Milligrams (mg)", value="mg"),
        app_commands.Choice(name="Pounds (lb)", value="lb"),
        app_commands.Choice(name="Ounces (oz)", value="oz"),
        app_commands.Choice(name="Stone (st)", value="stone"),
    ], to_unit=[
        app_commands.Choice(name="Kilograms (kg)", value="kg"),
        app_commands.Choice(name="Grams (g)", value="g"),
        app_commands.Choice(name="Milligrams (mg)", value="mg"),
        app_commands.Choice(name="Pounds (lb)", value="lb"),
        app_commands.Choice(name="Ounces (oz)", value="oz"),
        app_commands.Choice(name="Stone (st)", value="stone"),
    ])
    async def weight(self, interaction: discord.Interaction, value: float, from_unit: str, to_unit: str):
        try:
            result = _convert_weight(value, from_unit, to_unit)
            await interaction.response.send_message(f"⚖️ {value} {from_unit} = {result:.4f} {to_unit}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Weight conversion failed: {e}", ephemeral=True)

    @app_commands.command(name="timezone", description="Convert a date/time between timezones")
    @app_commands.describe(
        datetime_str="Date/time (e.g., '2024-01-05 15:30' or 'tomorrow 8pm')",
        from_timezone="Source timezone (e.g., UTC, America/New_York)",
        to_timezone="Target timezone (e.g., Europe/London)"
    )
    async def timezone(
        self,
        interaction: discord.Interaction,
        datetime_str: str,
        from_timezone: str = "UTC",
        to_timezone: str = "UTC"
    ):
        try:
            parsed = parser.parse(datetime_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo(from_timezone))
            else:
                parsed = parsed.astimezone(ZoneInfo(from_timezone))

            converted = parsed.astimezone(ZoneInfo(to_timezone))
            response = (
                f"🕒 **Time Conversion**\n"
                f"`{parsed.strftime('%Y-%m-%d %H:%M:%S %Z')}` → `{converted.strftime('%Y-%m-%d %H:%M:%S %Z')}`"
            )
            await interaction.response.send_message(response)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Timezone conversion failed: {e}",
                ephemeral=True
            )

    @app_commands.command(name="shoe", description="Convert shoe sizes between regions (US/UK/EU/cm)")
    @app_commands.describe(
        value="Shoe size value",
        from_system="Measurement system of the input size",
        to_system="Measurement system to convert to",
        gender="Men's or women's sizing"
    )
    @app_commands.choices(
        from_system=[
            app_commands.Choice(name="US", value="us"),
            app_commands.Choice(name="UK", value="uk"),
            app_commands.Choice(name="EU", value="eu"),
            app_commands.Choice(name="Centimeters", value="cm"),
        ],
        to_system=[
            app_commands.Choice(name="US", value="us"),
            app_commands.Choice(name="UK", value="uk"),
            app_commands.Choice(name="EU", value="eu"),
            app_commands.Choice(name="Centimeters", value="cm"),
        ],
        gender=[
            app_commands.Choice(name="Men", value="men"),
            app_commands.Choice(name="Women", value="women"),
        ]
    )
    async def shoe(
        self,
        interaction: discord.Interaction,
        value: float,
        from_system: str,
        to_system: str,
        gender: str = "men"
    ):
        try:
            result = _convert_shoe_size(value, from_system, to_system, gender)
            await interaction.response.send_message(
                f"👟 {gender.title()} size {value} ({from_system.upper()}) ≈ {result} ({to_system.upper()})"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Shoe size conversion failed: {e}", ephemeral=True)
