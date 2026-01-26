"""
Conversion command group (/convert …)
"""
import datetime as dt
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
import aiohttp
from typing import Optional
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


VOLUME_TO_ML = {
    "ml": 1.0,
    "l": 1000.0,
    "tsp": 4.92892,
    "tbsp": 14.7868,
    "floz": 29.5735,  # US fluid ounce
    "cup": 236.588,
    "pint": 473.176,
    "quart": 946.353,
    "gallon": 3785.41,
}


def _convert_volume(value: float, from_unit: str, to_unit: str) -> float:
    from_unit = from_unit.lower()
    to_unit = to_unit.lower()
    if from_unit not in VOLUME_TO_ML or to_unit not in VOLUME_TO_ML:
        raise ValueError("Unsupported volume unit")
    ml = value * VOLUME_TO_ML[from_unit]
    return ml / VOLUME_TO_ML[to_unit]


SHOE_LINEAR_COEFFS = {
    "men": {
        "us": {"slope": 0.64, "intercept": 20.56, "range": (3.5, 13.5)},
        "uk": {"slope": 0.64, "intercept": 20.88, "range": (3.0, 13.0)},
        "au": {"slope": 0.64, "intercept": 20.88, "range": (3.0, 13.0)},
        "eu": {"slope": 0.512, "intercept": 4.88, "range": (35.0, 47.5)},
        "jp": {"slope": 0.64, "intercept": 9.04, "range": (21.5, 31.5)},
        "china": {"slope": 0.46923, "intercept": 6.37692, "range": (35.0, 48.0)},
        "mex": {"slope": 0.5125, "intercept": 21.49375, "range": (4.5, 12.5)},
    },
    "women": {
        "us": {"slope": 0.60952, "intercept": 19.75238, "range": (5.0, 15.5)},
        "uk": {"slope": 0.60952, "intercept": 21.27619, "range": (2.5, 13.0)},
        "au": {"slope": 0.60952, "intercept": 20.66667, "range": (3.5, 14.0)},
        "eu": {"slope": 0.49231, "intercept": 5.56923, "range": (35.0, 48.0)},
        "jp": {"slope": 0.64, "intercept": 9.36, "range": (21.0, 31.0)},
        "china": {"slope": 0.512, "intercept": 4.624, "range": (35.5, 48.0)},
        "mex": {"slope": 0.5875, "intercept": 21.85625, "range": (4.5, 12.5)},
    }
}

SHOE_CM_RANGE = {
    "men": (22.8, 29.2),
    "women": (22.8, 29.2)
}

HALF_STEP_SYSTEMS = {"us", "uk", "au", "eu", "jp", "china", "mex"}


def _clamp(value: float, bounds: tuple[float, float] | None) -> float:
    if not bounds:
        return value
    lower, upper = bounds
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value


def _size_to_cm(system: str, size: float, gender: str) -> float:
    if system == "cm":
        return size
    if system == "in":
        return size * 2.54
    if system in ("kr", "mondo"):
        return size / 10.0

    coeffs = SHOE_LINEAR_COEFFS[gender].get(system)
    if not coeffs:
        raise ValueError("Unsupported shoe size system")
    size = _clamp(size, coeffs["range"])
    return (coeffs["slope"] * size) + coeffs["intercept"]


def _cm_to_size(system: str, cm_value: float, gender: str) -> float:
    cm_value = _clamp(cm_value, SHOE_CM_RANGE[gender])
    if system == "cm":
        return round(cm_value, 2)
    if system == "in":
        return round(cm_value / 2.54, 2)
    if system in ("kr", "mondo"):
        return round(cm_value * 10.0, 1)

    coeffs = SHOE_LINEAR_COEFFS[gender].get(system)
    if not coeffs:
        raise ValueError("Unsupported shoe size system")
    size = (cm_value - coeffs["intercept"]) / coeffs["slope"]
    size = _clamp(size, coeffs["range"])
    if system in HALF_STEP_SYSTEMS:
        # Round to nearest half-size for numbered systems
        return round(round(size * 2) / 2, 2)
    return round(size, 2)


def _convert_shoe_size(value: float, from_system: str, to_system: str, from_gender: str, to_gender: str) -> float:
    """
    Convert shoe sizes by normalizing to approximate foot length (cm) using
    linear formulas derived from the conversion charts (rather than a large lookup table).
    """
    from_system = from_system.lower()
    to_system = to_system.lower()
    from_gender = from_gender.lower()
    to_gender = to_gender.lower()
    if from_gender not in ("men", "women") or to_gender not in ("men", "women"):
        raise ValueError("Gender must be 'men' or 'women'")

    cm_len = _size_to_cm(from_system, value, from_gender)
    return _cm_to_size(to_system, cm_len, to_gender)


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

    @app_commands.command(name="liquid", description="Convert between common liquid/volume units")
    @app_commands.describe(
        value="Volume to convert",
        from_unit="Unit of the input value",
        to_unit="Unit to convert to"
    )
    @app_commands.choices(from_unit=[
        app_commands.Choice(name="Milliliters (ml)", value="ml"),
        app_commands.Choice(name="Liters (l)", value="l"),
        app_commands.Choice(name="Teaspoons (tsp)", value="tsp"),
        app_commands.Choice(name="Tablespoons (tbsp)", value="tbsp"),
        app_commands.Choice(name="Fluid Ounces (fl oz)", value="floz"),
        app_commands.Choice(name="Cups", value="cup"),
        app_commands.Choice(name="Pints", value="pint"),
        app_commands.Choice(name="Quarts", value="quart"),
        app_commands.Choice(name="Gallons", value="gallon"),
    ], to_unit=[
        app_commands.Choice(name="Milliliters (ml)", value="ml"),
        app_commands.Choice(name="Liters (l)", value="l"),
        app_commands.Choice(name="Teaspoons (tsp)", value="tsp"),
        app_commands.Choice(name="Tablespoons (tbsp)", value="tbsp"),
        app_commands.Choice(name="Fluid Ounces (fl oz)", value="floz"),
        app_commands.Choice(name="Cups", value="cup"),
        app_commands.Choice(name="Pints", value="pint"),
        app_commands.Choice(name="Quarts", value="quart"),
        app_commands.Choice(name="Gallons", value="gallon"),
    ])
    async def liquid(self, interaction: discord.Interaction, value: float, from_unit: str, to_unit: str):
        try:
            result = _convert_volume(value, from_unit, to_unit)
            await interaction.response.send_message(f"🥤 {value} {from_unit} = {result:.4f} {to_unit}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Liquid conversion failed: {e}", ephemeral=True)

    @app_commands.command(name="currency", description="Convert currencies with live or historical rates")
    @app_commands.describe(
        amount="Amount to convert",
        from_currency="Three-letter code to convert from (e.g., USD)",
        to_currency="Three-letter code to convert to (e.g., EUR)",
        date="Optional historical date (YYYY-MM-DD). Default: latest rate"
    )
    async def currency(
        self,
        interaction: discord.Interaction,
        amount: float,
        from_currency: str,
        to_currency: str,
        date: Optional[str] = None
    ):
        """Fetch rate from exchangerate.host and convert the amount."""
        from_code = from_currency.upper()
        to_code = to_currency.upper()

        # Basic validation
        if len(from_code) != 3 or len(to_code) != 3:
            await interaction.response.send_message("❌ Currency codes must be 3 letters (e.g., USD, EUR).", ephemeral=True)
            return

        query_date = "latest"
        if date:
            try:
                parsed_date = dt.datetime.fromisoformat(date).date()
                query_date = parsed_date.isoformat()
            except Exception:
                await interaction.response.send_message("❌ Invalid date format. Use YYYY-MM-DD.", ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)

        url = f"https://api.exchangerate.host/{query_date}"
        params = {"base": from_code, "symbols": to_code}

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"❌ Rate lookup failed (HTTP {resp.status}).", ephemeral=True)
                        return
                    data = await resp.json()
        except Exception as e:
            await interaction.followup.send(f"❌ Error calling rate API: {e}", ephemeral=True)
            return

        rate = (data or {}).get("rates", {}).get(to_code)
        effective_date = (data or {}).get("date") or query_date
        if rate is None:
            await interaction.followup.send("❌ Could not find that currency pair.", ephemeral=True)
            return

        converted = amount * rate
        await interaction.followup.send(
            f"💱 {amount:.2f} {from_code} = {converted:.2f} {to_code}\n"
            f"Rate: {rate:.6f} ({effective_date})",
            ephemeral=False
        )

    @app_commands.command(name="inflation", description="Calculate inflation between two dates for a currency")
    @app_commands.describe(
        amount="Amount in the original currency",
        currency="Three-letter currency code (e.g., USD, EUR, GBP)",
        from_date="Starting date (YYYY-MM-DD)",
        to_date="Ending date (YYYY-MM-DD, default: today)"
    )
    async def inflation(
        self,
        interaction: discord.Interaction,
        amount: float,
        currency: str,
        from_date: str,
        to_date: Optional[str] = None
    ):
        """Calculate purchasing power change between two dates using currency exchange rate changes as a proxy."""
        currency_code = currency.upper()
        
        # Validate currency code
        if len(currency_code) != 3:
            await interaction.response.send_message("❌ Currency code must be 3 letters (e.g., USD, EUR).", ephemeral=True)
            return
        
        # Parse dates
        try:
            parsed_from = dt.datetime.fromisoformat(from_date).date()
            from_date_str = parsed_from.isoformat()
        except Exception:
            await interaction.response.send_message("❌ Invalid from_date format. Use YYYY-MM-DD.", ephemeral=True)
            return
        
        if to_date:
            try:
                parsed_to = dt.datetime.fromisoformat(to_date).date()
                to_date_str = parsed_to.isoformat()
            except Exception:
                await interaction.response.send_message("❌ Invalid to_date format. Use YYYY-MM-DD.", ephemeral=True)
                return
        else:
            parsed_to = dt.date.today()
            to_date_str = "latest"
        
        # Ensure from_date is before to_date
        if parsed_from >= parsed_to:
            await interaction.response.send_message("❌ from_date must be before to_date.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=False)
        
        # Fetch exchange rates for both dates using USD as base
        # This gives us a proxy for relative currency value changes
        base = "USD"
        url_from = f"https://api.exchangerate.host/{from_date_str}"
        url_to = f"https://api.exchangerate.host/{to_date_str}"
        params = {"base": base, "symbols": currency_code}
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Get rate for from_date
                async with session.get(url_from, params=params) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"❌ Rate lookup failed for {from_date_str} (HTTP {resp.status}).", ephemeral=True)
                        return
                    data_from = await resp.json()
                
                # Get rate for to_date
                async with session.get(url_to, params=params) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"❌ Rate lookup failed for {to_date_str} (HTTP {resp.status}).", ephemeral=True)
                        return
                    data_to = await resp.json()
        except Exception as e:
            await interaction.followup.send(f"❌ Error calling rate API: {e}", ephemeral=True)
            return
        
        rate_from = (data_from or {}).get("rates", {}).get(currency_code)
        rate_to = (data_to or {}).get("rates", {}).get(currency_code)
        actual_from_date = (data_from or {}).get("date", from_date_str)
        actual_to_date = (data_to or {}).get("date", to_date_str)
        
        if rate_from is None or rate_to is None:
            await interaction.followup.send(f"❌ Could not find rates for {currency_code}.", ephemeral=True)
            return
        
        # Calculate the change in value
        # If the currency strengthened against USD, its purchasing power increased
        value_change_ratio = rate_to / rate_from
        adjusted_amount = amount * value_change_ratio
        
        # Calculate percentage change
        percent_change = ((value_change_ratio - 1) * 100)
        
        # Build response
        embed = discord.Embed(
            title="📊 Inflation Calculator",
            color=discord.Color.blue() if percent_change >= 0 else discord.Color.red()
        )
        
        embed.add_field(
            name="Original Amount",
            value=f"{amount:.2f} {currency_code} ({actual_from_date})",
            inline=False
        )
        
        embed.add_field(
            name="Adjusted Amount",
            value=f"{adjusted_amount:.2f} {currency_code} ({actual_to_date})",
            inline=False
        )
        
        change_emoji = "📈" if percent_change >= 0 else "📉"
        embed.add_field(
            name="Value Change",
            value=f"{change_emoji} {percent_change:+.2f}%",
            inline=False
        )
        
        years_diff = (parsed_to - parsed_from).days / 365.25
        if years_diff > 0:
            annual_rate = ((value_change_ratio ** (1 / years_diff)) - 1) * 100
            embed.add_field(
                name="Annualized Rate",
                value=f"{annual_rate:+.2f}% per year",
                inline=False
            )
        
        embed.set_footer(text=f"Note: Using {base}-based exchange rate changes as proxy for purchasing power")
        
        await interaction.followup.send(embed=embed)

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

    @app_commands.command(name="shoe", description="Convert shoe sizes between various regions")
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
