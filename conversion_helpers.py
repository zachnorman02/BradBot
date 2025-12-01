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
    daily_dose = dose / frequency
    gel_absorption = 0.1
    cyp_absorption = 0.95
    
    if starting_type == "gel":
        absorption = daily_dose * gel_absorption
        weekly = absorption * 7
        final = weekly / cyp_absorption
        return f"{dose}mg gel every {frequency} days is approximately {final:.2f}mg cypionate weekly."
    elif starting_type == "cypionate":
        absorption = daily_dose * cyp_absorption
        final = absorption / gel_absorption
        return f"{dose}mg cypionate every {frequency} days is approximately {final:.2f}mg gel daily."
    else:
        return "❌ Invalid conversion type."
