"""Address-count preferences, shared by the API and offline engine."""
import math


def address_preferences(target=None, tolerance=15, minimum=None, maximum=None):
    def whole(value, label, lower=50):
        if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= 10000:
            raise ValueError(f"{label} must be a whole number from {lower} to 10,000.")
        return value
    if minimum is not None or maximum is not None:
        lo, hi = whole(minimum, "Range minimum",1), whole(maximum, "Range maximum",1)
        if lo >= hi:
            raise ValueError("Range minimum must be less than range maximum.")
        target = math.floor((lo + hi) / 2+.5)
        if target<50:
            raise ValueError("The preferred range must have a midpoint of at least 50 addresses.")
        tolerance = (hi - lo) * 50 / target
        source = "range"
    elif target is not None:
        target = whole(target, "Preferred address count")
        lo = hi = None
        source = "target"
    else:
        return {"mode": "natural", "target_addresses": None, "tolerance_percent": None,
                "preferred_minimum": None, "maximum_addresses": None, "range_adjusted": False}
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance > (100 if source=='range' else 50) or tolerance < 0:
        raise ValueError("Tolerance must be a percentage between 0 and 50; values below 10 use 10%.")
    adjusted = tolerance < 10
    tolerance = max(10, tolerance)
    return {"mode": "target", "preference_input": source, "target_addresses": target,
            "tolerance_percent": round(tolerance, 4),
            "preferred_minimum": math.ceil(target * (1 - tolerance / 100)) if source == "target" or adjusted else lo,
            "maximum_addresses": math.floor(target * (1 + tolerance / 100)) if source == "target" or adjusted else hi,
            "range_adjusted": adjusted,
            "smaller_natural_areas_allowed": True, "target_is_hard_capacity": False}
