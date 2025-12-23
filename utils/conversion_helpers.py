"""
Conversion utilities for testosterone and other medical calculations
"""
import enum


class ConversionType(str, enum.Enum):
    """Types of testosterone administration"""
    CYPIONATE = "cypionate"
    GEL = "gel"


def convert_testosterone(starting_type: str, dose: float, frequency: int) -> str:
    """
    Converts between testosterone cypionate and gel doses.
    
    Args:
        starting_type: Type of testosterone ("cypionate" or "gel")
        dose: Dose amount (in mg or ml)
        frequency: Frequency of dose (in days)
        
    Returns:
        Conversion result as a formatted string
    """
    # Assumptions based on provided guidance:
    # - Gel absorbs ~12.5%
    # - 30% of a cypionate injection is carrier oil, so 70% of the labeled dose is active testosterone
    gel_absorption = 0.125
    cyp_active_fraction = 0.70
    doses_per_week = 7 / frequency

    if starting_type == "gel":
        weekly_absorbed = dose * doses_per_week * gel_absorption
        cyp_weekly = weekly_absorbed / cyp_active_fraction
        return (
            f"{dose}mg gel every {frequency} day(s) absorbs about {weekly_absorbed:.2f}mg weekly. "
            f"Equivalent cypionate: ~{cyp_weekly:.2f}mg per week "
            f"(12.5% gel absorption, 70% active cypionate)."
        )
    if starting_type == "cypionate":
        weekly_absorbed = dose * doses_per_week * cyp_active_fraction
        gel_daily = weekly_absorbed / (7 * gel_absorption)
        return (
            f"{dose}mg cypionate every {frequency} day(s) absorbs about {weekly_absorbed:.2f}mg weekly. "
            f"Equivalent gel: ~{gel_daily:.2f}mg per day "
            f"(70% active cypionate, 12.5% gel absorption)."
        )
    return "❌ Invalid conversion type."
