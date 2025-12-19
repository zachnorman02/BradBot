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


SHOE_TABLE = [
    {"uk": 3.0, "eu": 35.0, "us": 3.5, "au": 3.0, "jp": 21.5, "china": 35.0, "mex": None, "kr": 228.0, "mondo": 228.0, "cm": 22.8, "in": 9.0},
    {"uk": 3.5, "eu": 35.5, "us": 4.0, "au": 3.5, "jp": 22.0, "china": 36.0, "mex": None, "kr": 231.0, "mondo": 231.0, "cm": 23.1, "in": 9.125},
    {"uk": 4.0, "eu": 36.0, "us": 4.5, "au": 4.0, "jp": 22.5, "china": 37.0, "mex": None, "kr": 235.0, "mondo": 235.0, "cm": 23.5, "in": 9.25},
    {"uk": 4.5, "eu": 37.0, "us": 5.0, "au": 4.5, "jp": 23.0, "china": 38.0, "mex": 4.5, "kr": 238.0, "mondo": 238.0, "cm": 23.8, "in": 9.375},
    {"uk": 5.0, "eu": 37.5, "us": 5.5, "au": 5.0, "jp": 23.5, "china": 39.0, "mex": 5.0, "kr": 241.0, "mondo": 241.0, "cm": 24.1, "in": 9.5},
    {"uk": 5.5, "eu": 38.0, "us": 6.0, "au": 5.5, "jp": 24.0, "china": 39.5, "mex": 5.5, "kr": 245.0, "mondo": 245.0, "cm": 24.5, "in": 9.625},
    {"uk": 6.0, "eu": 38.5, "us": 6.5, "au": 6.0, "jp": 24.5, "china": 40.0, "mex": 6.0, "kr": 248.0, "mondo": 248.0, "cm": 24.8, "in": 9.75},
    {"uk": 6.5, "eu": 39.0, "us": 7.0, "au": 6.5, "jp": 25.0, "china": 41.0, "mex": 6.5, "kr": 251.0, "mondo": 251.0, "cm": 25.1, "in": 9.875},
    {"uk": 7.0, "eu": 40.0, "us": 7.5, "au": 7.0, "jp": 25.5, "china": None, "mex": 7.0, "kr": 254.0, "mondo": 254.0, "cm": 25.4, "in": 10.0},
    {"uk": 7.5, "eu": 41.0, "us": 8.0, "au": 7.5, "jp": 26.0, "china": 42.0, "mex": 7.5, "kr": 257.0, "mondo": 257.0, "cm": 25.7, "in": 10.125},
    {"uk": 8.0, "eu": 42.0, "us": 8.5, "au": 8.0, "jp": 26.5, "china": 43.0, "mex": 9.0, "kr": 260.0, "mondo": 260.0, "cm": 26.0, "in": 10.25},
    {"uk": 8.5, "eu": 43.0, "us": 9.0, "au": 8.5, "jp": 27.0, "china": 43.5, "mex": None, "kr": 263.0, "mondo": 263.0, "cm": 26.3, "in": 10.375},
    {"uk": 9.0, "eu": 43.5, "us": 9.5, "au": 9.0, "jp": 27.5, "china": 44.0, "mex": 10.0, "kr": 267.0, "mondo": 267.0, "cm": 26.7, "in": 10.5},
    {"uk": 9.5, "eu": 44.0, "us": 10.0, "au": 9.5, "jp": 28.0, "china": 44.5, "mex": None, "kr": 270.0, "mondo": 270.0, "cm": 27.0, "in": 10.75},
    {"uk": 10.0, "eu": 44.5, "us": 10.5, "au": 10.0, "jp": 28.5, "china": 45.0, "mex": 11.0, "kr": 273.0, "mondo": 273.0, "cm": 27.3, "in": 10.875},
    {"uk": 10.5, "eu": 45.0, "us": 11.0, "au": 10.5, "jp": 29.0, "china": 46.0, "mex": None, "kr": 276.0, "mondo": 276.0, "cm": 27.6, "in": 10.875},
    {"uk": 11.0, "eu": 45.5, "us": 11.5, "au": 11.0, "jp": 29.5, "china": None, "mex": 12.5, "kr": 279.0, "mondo": 279.0, "cm": 27.9, "in": 11.0},
    {"uk": 11.5, "eu": 46.0, "us": 12.0, "au": 11.5, "jp": 30.0, "china": 47.0, "mex": None, "kr": 283.0, "mondo": 283.0, "cm": 28.3, "in": 11.125},
    {"uk": 12.0, "eu": 46.5, "us": 12.5, "au": 12.0, "jp": 30.5, "china": 47.5, "mex": None, "kr": 286.0, "mondo": 286.0, "cm": 28.6, "in": 11.25},
    {"uk": 12.5, "eu": 47.0, "us": 13.0, "au": 12.5, "jp": 31.0, "china": 48.0, "mex": None, "kr": 289.0, "mondo": 289.0, "cm": 28.9, "in": 11.375},
    {"uk": 13.0, "eu": 47.5, "us": 13.5, "au": 13.0, "jp": 31.5, "china": None, "mex": None, "kr": 292.0, "mondo": 292.0, "cm": 29.2, "in": 11.5},
]

# Shoe lookup table represents men's numbering for systems where genders differ (US/UK/AU).
GENDER_SPECIFIC_TABLE_SYSTEMS = {"us", "uk", "au"}


def _table_lookup_to_cm(system: str, value: float) -> float | None:
    entries = []
    for row in SHOE_TABLE:
        size = row.get(system)
        cm = row.get("cm")
        if size is None or cm is None:
            continue
        entries.append((size, cm))
    if not entries:
        return None
    entries.sort(key=lambda x: x[0])
    # Exact match
    for size, cm in entries:
        if abs(size - value) < 1e-6:
            return cm
    # Clamp
    if value <= entries[0][0]:
        return entries[0][1]
    if value >= entries[-1][0]:
        return entries[-1][1]
    # Interpolate
    for i in range(1, len(entries)):
        prev_size, prev_cm = entries[i - 1]
        next_size, next_cm = entries[i]
        if prev_size <= value <= next_size:
            ratio = (value - prev_size) / (next_size - prev_size)
            return prev_cm + ratio * (next_cm - prev_cm)
    return None


def _table_lookup_from_cm(system: str, cm_value: float) -> float | None:
    entries = []
    for row in SHOE_TABLE:
        cm = row.get("cm")
        size = row.get(system)
        if cm is None or size is None:
            continue
        entries.append((cm, size))
    if not entries:
        return None
    entries.sort(key=lambda x: x[0])
    for cm, size in entries:
        if abs(cm - cm_value) < 1e-6:
            return size
    if cm_value <= entries[0][0]:
        return entries[0][1]
    if cm_value >= entries[-1][0]:
        return entries[-1][1]
    for i in range(1, len(entries)):
        prev_cm, prev_size = entries[i - 1]
        next_cm, next_size = entries[i]
        if prev_cm <= cm_value <= next_cm:
            ratio = (cm_value - prev_cm) / (next_cm - prev_cm)
            return prev_size + ratio * (next_size - prev_size)
    return None


def _convert_shoe_size(value: float, from_system: str, to_system: str, from_gender: str, to_gender: str) -> float:
    """
    Convert shoe sizes by normalizing to approximate foot length (cm).
    Notes: lookup table stores men's numbering for US/UK/AU rows; women's results
    are derived by applying the traditional offsets when translating to/from cm.
    """
    from_system = from_system.lower()
    to_system = to_system.lower()
    from_gender = from_gender.lower()
    to_gender = to_gender.lower()
    if from_gender not in ("men", "women") or to_gender not in ("men", "women"):
        raise ValueError("Gender must be 'men' or 'women'")

    def _use_table(system: str, gender: str) -> bool:
        return system not in GENDER_SPECIFIC_TABLE_SYSTEMS or gender == "men"

    def length_cm(system: str, size: float, gender: str) -> float:
        table_cm = _table_lookup_to_cm(system, size) if _use_table(system, gender) else None
        if table_cm is not None:
            return table_cm
        if system == "cm":
            return size
        if system == "in":
            return size * 2.54
        if system in ("kr", "mondo"):
            return size / 10.0
        if system == "eu":
            return (size / 1.5) - 1.5
        if system == "us":
            inches = (size + (22 if gender == "men" else 21)) / 3
            return inches * 2.54
        if system in ("uk", "au"):
            inches = (size + 23) / 3
            return inches * 2.54
        raise ValueError("Unsupported shoe size system")

    def size_from_cm(system: str, cm: float, gender: str) -> float:
        table_size = _table_lookup_from_cm(system, cm) if _use_table(system, gender) else None
        if table_size is not None:
            return round(table_size, 2)
        if system == "cm":
            return round(cm, 2)
        if system == "in":
            return round(cm / 2.54, 2)
        if system in ("kr", "mondo"):
            return round(cm * 10, 1)
        if system == "eu":
            return round((cm + 1.5) * 1.5, 1)
        inches = cm / 2.54
        if system == "us":
            return round((3 * inches) - (22 if gender == "men" else 21), 1)
        if system in ("uk", "au"):
            return round((3 * inches) - 23, 1)
        raise ValueError("Unsupported shoe size system")

    cm_len = length_cm(from_system, value, from_gender)
    return size_from_cm(to_system, cm_len, to_gender)


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

    @app_commands.command(name="shoe", description="Convert shoe sizes between regions (US/CA, UK, AU, EU, JP, China, Mexico, Korea, Mondopoint, cm, inches)")
    @app_commands.describe(
        value="Shoe size value",
        from_system="Measurement system of the input size",
        to_system="Measurement system to convert to",
        from_gender="Men's or women's sizing for the input value",
        to_gender="Men's or women's sizing for the output value"
    )
    @app_commands.choices(
        from_system=[
            app_commands.Choice(name="US / Canada", value="us"),
            app_commands.Choice(name="UK", value="uk"),
            app_commands.Choice(name="Australia / NZ", value="au"),
            app_commands.Choice(name="EU", value="eu"),
            app_commands.Choice(name="Japan", value="jp"),
            app_commands.Choice(name="China", value="china"),
            app_commands.Choice(name="Mexico", value="mex"),
            app_commands.Choice(name="Korea (mm)", value="kr"),
            app_commands.Choice(name="Mondopoint (mm)", value="mondo"),
            app_commands.Choice(name="Centimeters", value="cm"),
            app_commands.Choice(name="Inches", value="in"),
        ],
        to_system=[
            app_commands.Choice(name="US / Canada", value="us"),
            app_commands.Choice(name="UK", value="uk"),
            app_commands.Choice(name="Australia / NZ", value="au"),
            app_commands.Choice(name="EU", value="eu"),
            app_commands.Choice(name="Japan", value="jp"),
            app_commands.Choice(name="China", value="china"),
            app_commands.Choice(name="Mexico", value="mex"),
            app_commands.Choice(name="Korea (mm)", value="kr"),
            app_commands.Choice(name="Mondopoint (mm)", value="mondo"),
            app_commands.Choice(name="Centimeters", value="cm"),
            app_commands.Choice(name="Inches", value="in"),
        ],
        from_gender=[
            app_commands.Choice(name="Men", value="men"),
            app_commands.Choice(name="Women", value="women"),
        ],
        to_gender=[
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
        from_gender: str = "men",
        to_gender: str = "men"
    ):
        try:
            result = _convert_shoe_size(value, from_system, to_system, from_gender, to_gender)
            await interaction.response.send_message(
                f"👟 {from_gender.title()} size {value} ({from_system.upper()}) ≈ "
                f"{result} ({to_gender.title()} {to_system.upper()})"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Shoe size conversion failed: {e}", ephemeral=True)
