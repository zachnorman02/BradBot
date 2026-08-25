"""Shared Choice-list constants for /convert, generated once from a single
{value: display_name} dict per unit family instead of the old pattern of
writing out the same Choice list twice (once for from_unit, once for
to_unit) on every command."""
from discord import app_commands

TEMPERATURE_UNITS = {"c": "Celsius (°C)", "f": "Fahrenheit (°F)", "k": "Kelvin (K)"}
LENGTH_UNITS = {
    "m": "Meters (m)", "km": "Kilometers (km)", "cm": "Centimeters (cm)", "mm": "Millimeters (mm)",
    "mi": "Miles (mi)", "ft": "Feet (ft)", "in": "Inches (in)", "yd": "Yards (yd)",
}
WEIGHT_UNITS = {
    "kg": "Kilograms (kg)", "g": "Grams (g)", "mg": "Milligrams (mg)",
    "lb": "Pounds (lb)", "oz": "Ounces (oz)", "stone": "Stone (st)",
}
VOLUME_UNITS = {
    "ml": "Milliliters (ml)", "l": "Liters (l)", "tsp": "Teaspoons (tsp)", "tbsp": "Tablespoons (tbsp)",
    "floz": "Fluid Ounces (fl oz)", "cup": "Cups", "pint": "Pints", "quart": "Quarts", "gallon": "Gallons",
}
SHOE_SYSTEMS = {
    "us": "US / Canada", "uk": "UK", "au": "Australia / NZ", "eu": "EU", "jp": "Japan",
    "china": "China", "mex": "Mexico", "kr": "Korea (mm)", "mondo": "Mondopoint (mm)",
    "cm": "Centimeters", "in": "Inches",
}
SHOE_GENDERS = {"men": "Men", "women": "Women"}


def _choices(units: dict) -> list[app_commands.Choice]:
    return [app_commands.Choice(name=label, value=key) for key, label in units.items()]


TEMPERATURE_CHOICES = _choices(TEMPERATURE_UNITS)
LENGTH_CHOICES = _choices(LENGTH_UNITS)
WEIGHT_CHOICES = _choices(WEIGHT_UNITS)
VOLUME_CHOICES = _choices(VOLUME_UNITS)
SHOE_SYSTEM_CHOICES = _choices(SHOE_SYSTEMS)
SHOE_GENDER_CHOICES = _choices(SHOE_GENDERS)
