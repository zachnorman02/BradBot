"""Pure conversion math for the /convert domain."""

LENGTH_TO_METERS = {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "mi": 1609.34, "ft": 0.3048, "in": 0.0254, "yd": 0.9144}
WEIGHT_TO_KG = {"kg": 1.0, "g": 0.001, "mg": 0.000001, "lb": 0.453592, "oz": 0.0283495, "stone": 6.35029}
VOLUME_TO_ML = {"ml": 1.0, "l": 1000.0, "tsp": 4.92892, "tbsp": 14.7868, "floz": 29.5735, "cup": 236.588, "pint": 473.176, "quart": 946.353, "gallon": 3785.41}

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
    },
}
SHOE_CM_RANGE = {"men": (22.8, 29.2), "women": (22.8, 29.2)}
HALF_STEP_SYSTEMS = {"us", "uk", "au", "eu", "jp", "china", "mex"}


def convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    from_unit, to_unit = from_unit.lower(), to_unit.lower()
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


def convert_length(value: float, from_unit: str, to_unit: str) -> float:
    from_unit, to_unit = from_unit.lower(), to_unit.lower()
    if from_unit not in LENGTH_TO_METERS or to_unit not in LENGTH_TO_METERS:
        raise ValueError("Unsupported length unit")
    return value * LENGTH_TO_METERS[from_unit] / LENGTH_TO_METERS[to_unit]


def convert_weight(value: float, from_unit: str, to_unit: str) -> float:
    from_unit, to_unit = from_unit.lower(), to_unit.lower()
    if from_unit not in WEIGHT_TO_KG or to_unit not in WEIGHT_TO_KG:
        raise ValueError("Unsupported weight unit")
    return value * WEIGHT_TO_KG[from_unit] / WEIGHT_TO_KG[to_unit]


def convert_volume(value: float, from_unit: str, to_unit: str) -> float:
    from_unit, to_unit = from_unit.lower(), to_unit.lower()
    if from_unit not in VOLUME_TO_ML or to_unit not in VOLUME_TO_ML:
        raise ValueError("Unsupported volume unit")
    return value * VOLUME_TO_ML[from_unit] / VOLUME_TO_ML[to_unit]


def _clamp(value: float, bounds: tuple[float, float] | None) -> float:
    if not bounds:
        return value
    lower, upper = bounds
    return max(lower, min(upper, value))


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
        return round(round(size * 2) / 2, 2)
    return round(size, 2)


def convert_shoe_size(value: float, from_system: str, to_system: str, from_gender: str, to_gender: str) -> float:
    """Convert shoe sizes by normalizing to approximate foot length (cm)
    using linear formulas derived from the conversion charts."""
    from_system, to_system = from_system.lower(), to_system.lower()
    from_gender, to_gender = from_gender.lower(), to_gender.lower()
    if from_gender not in ("men", "women") or to_gender not in ("men", "women"):
        raise ValueError("Gender must be 'men' or 'women'")

    cm_len = _size_to_cm(from_system, value, from_gender)
    return _cm_to_size(to_system, cm_len, to_gender)
