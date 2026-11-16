"""One validated operating record shared by the form, solver and exports."""
from copy import deepcopy
import math
from partition_app.inputs import InputError


DEFAULTS = {
    "crew_start": "06:15", "pretrip_minutes": 15, "break_minutes": 30,
    "unpaid_lunch_minutes": 0, "posttrip_minutes": 0, "fueling_minutes": 0,
    "preferred_paid_hours": 8, "earliest_return":"14:30", "preferred_return":"15:30", "latest_return": "16:45",
    "minimum_paid_hours":4,
    "general_speed_factor": .95, "active_speed_factor": .855,
    "reversal_seconds": 30, "reversal_sensitivity_seconds": 60,
    "search_seconds_per_section": 12, "fleet_search_seconds": 120,
    "local_solver_workers": 2,
    "table_locations": 800, "available_trucks_comparison": 45,
    "garbage_trucks_comparison":17, "recycling_trucks_comparison":12,
    "yard": {"name": "385 Eagle Drive", "address": "385 Eagle Drive, Rosser / Winnipeg",
             "lat": 49.936144, "lon": -97.2318821,
             "coordinate_source": "Mapped access for the user-supplied yard"},
    "garbage": {"name": "Garbage", "equipment": "ASL", "capacity": 615,
                "capacity_low": 580, "capacity_high": 650, "capacity_tolerance_percent": 0, "payload_tonnes": 9,
                "pickup_seconds":12.5,"pickup_seconds_low":10,"pickup_seconds_high":15,
                "observed_pickups_per_minute_low":3,"observed_pickups_per_minute_high":3.5,
                "active_collection_pickups_per_minute":3.25,"use_observed_collection_pace":True,
                "kg_per_pickup": None,
                "receiver": {"name": "Brady Landfill", "address": "1777 Brady Road",
                             "lat": 49.75777887724071, "lon": -97.21293184399106,
                             "opens": "06:00", "closes": "18:00", "onsite_minutes": 15,
                             "coordinate_source": "Frozen City address point and mapped facility access",
                             "summer_opens": "05:00", "summer_closes": "19:00"}},
    "recycling": {"name": "Recycling", "equipment": "Rear load", "capacity": 1300,
                  "capacity_low": 1200, "capacity_high": 1350, "capacity_tolerance_percent": 2,
                  "pickup_seconds":8.5,"pickup_seconds_low":7,"pickup_seconds_high":10,
                  "use_observed_collection_pace":False,
                  "receiver": {"name": "Canada Fibers / GFL MRF", "address": "335 Mazenod Road",
                               "lat": 49.87533514341649, "lon": -97.04855126235479,
                               "opens": "06:00", "closes": "18:00", "onsite_minutes": 15,
                               "coordinate_source": "Frozen City address point and mapped facility access"}},
    "collection_access": "curbside", "collection_side": "right",
    "pickups_per_address_per_stream": 1, "preserve_planning_sections": True,
    "allow_shared_overlong_sections": True,
    "final_unload_required": True, "loads_per_truck": "optimized",
    "reference_loads_per_truck": 2,
    "objective":"trucks_then_paid_time",
    "load_underfill_seconds_per_pickup":1.,
    "minimum_dump_fill_percent":60,
    "dump_shortfall_seconds_per_pickup":30.,
    "overflow_seconds_per_pickup":30.,
}


def stream_settings(config,stream):
    return {**config,**config[stream]}


def load_limits(config, stream):
    """Normal pickup capacity and the explicit bounded scenario maximum."""
    cfg=config[stream]
    normal=cfg['capacity_high']
    maximum=normal+math.floor(normal*cfg.get('capacity_tolerance_percent',0)/100+1e-9)
    if stream=='garbage' and cfg.get('kg_per_pickup'):
        payload=math.floor(cfg['payload_tonnes']*1000/cfg['kg_per_pickup'])
        normal=min(normal,payload);maximum=min(maximum,payload)
    return normal,maximum


def clock_seconds(value):
    try:
        h, m = map(int, value.split(":"))
        if not 0 <= h < 24 or not 0 <= m < 60:
            raise ValueError()
        return h * 3600 + m * 60
    except (ValueError, AttributeError):
        raise InputError("Times must use HH:MM on the same working day.")


def clock_label(seconds):
    minutes = round(seconds / 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def settings(payload=None):
    result = deepcopy(DEFAULTS)
    payload=deepcopy(payload or {})
    # Retire the previous ownership rule. The user's later instruction permits
    # clean work-area sharing while keeping the planning geography unchanged.
    payload.pop('preserve_whole_sections',None)
    for key in ['pickup_seconds','pickup_seconds_low','pickup_seconds_high','observed_pickups_per_minute_low',
                'observed_pickups_per_minute_high','active_collection_pickups_per_minute','use_observed_collection_pace']:
        if key in payload:payload.setdefault('garbage',{})[key]=payload.pop(key)
    def merge(dest, update):
        if not isinstance(update, dict):
            raise InputError("Routing settings must be an object.")
        for k, v in update.items():
            if k not in dest:
                raise InputError(f"Unknown routing setting: {k}")
            if isinstance(dest[k], dict):
                merge(dest[k], v)
            else:
                dest[k] = v
    merge(result, payload or {})
    # Historical scenarios without a preferred window keep their original
    # earliest return; loading them must not silently tighten their constraints.
    if 'preferred_return' not in payload and ('earliest_return' in payload or 'latest_return' in payload):
        result['preferred_return']=result['earliest_return']
    def number(obj, key, lo, hi, integer=False, nullable=False):
        v = obj[key]
        if nullable and v is None:
            return
        if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not lo <= v <= hi or (integer and int(v) != v):
            raise InputError(f"{key.replace('_', ' ')} must be {'a whole number ' if integer else ''}between {lo} and {hi}.")
    for k in ["pretrip_minutes", "break_minutes", "unpaid_lunch_minutes", "posttrip_minutes", "fueling_minutes"]:
        number(result, k, 0, 180)
    for stream in ['garbage','recycling']:
        for k in ['pickup_seconds','pickup_seconds_low','pickup_seconds_high']:number(result[stream],k,1,300)
        if not result[stream]['pickup_seconds_low'] <= result[stream]['pickup_seconds'] <= result[stream]['pickup_seconds_high']:
            raise InputError(f'{stream.title()} stationary pickup time must be inside its low/high range.')
        if not isinstance(result[stream]['use_observed_collection_pace'],bool):
            raise InputError('Use observed collection pace must be true or false.')
    if result['recycling']['use_observed_collection_pace']:
        raise InputError('Recycling uses stationary pickup plus measured driving; no combined pace was supplied.')
    garbage=result['garbage']
    for k in ['observed_pickups_per_minute_low','observed_pickups_per_minute_high','active_collection_pickups_per_minute']:
        number(garbage,k,.1,20)
    if not garbage['observed_pickups_per_minute_low'] <= garbage['active_collection_pickups_per_minute'] <= garbage['observed_pickups_per_minute_high']:
        raise InputError('Active collection pace must be inside the observed range.')
    number(result, "preferred_paid_hours", 1, 16)
    number(result,'minimum_paid_hours',0,16)
    for k in ["general_speed_factor", "active_speed_factor"]:
        number(result, k, .2, 1.5)
    for k in ["reversal_seconds", "reversal_sensitivity_seconds"]:
        number(result, k, 0, 300)
    number(result, "search_seconds_per_section", 1, 120, True)
    number(result, "fleet_search_seconds", 1, 300, True)
    number(result, "local_solver_workers", 1, 4, True)
    number(result, "table_locations", 20, 5000, True)
    number(result, "available_trucks_comparison", 1, 500, True)
    for stream in ['garbage','recycling']:
        number(result, stream+'_trucks_comparison', 1, 500, True)
    number(result,'load_underfill_seconds_per_pickup',0,30)
    number(result,'minimum_dump_fill_percent',0,100)
    number(result,'dump_shortfall_seconds_per_pickup',0,300)
    number(result,'overflow_seconds_per_pickup',0,300)
    start = clock_seconds(result["crew_start"])
    end = clock_seconds(result["latest_return"])
    if not start < clock_seconds(result['earliest_return']) < end:
        raise InputError('Earliest return must be between crew start and latest return.')
    if not clock_seconds(result['earliest_return']) <= clock_seconds(result['preferred_return']) <= end:
        raise InputError('Preferred return must be between earliest and latest return.')
    if start + result["pretrip_minutes"] * 60 >= end:
        raise InputError("Latest return must be after crew start and pretrip.")
    for site in [result["yard"], *[result[s]["receiver"] for s in ["garbage", "recycling"]]]:
        number(site, "lat", 49.23, 50.53)
        number(site, "lon", -98.25, -96.20)
        for k in ["name", "address", "coordinate_source"]:
            if not isinstance(site[k], str) or not 1 <= len(site[k]) <= 400:
                raise InputError(f"A valid facility {k} is required.")
        if "opens" in site:
            if clock_seconds(site["opens"]) >= clock_seconds(site["closes"]):
                raise InputError("Receiver closing time must be after opening time.")
            number(site, "onsite_minutes", 0, 180)
    for stream in ["garbage", "recycling"]:
        number(result[stream],'capacity_tolerance_percent',0,20)
        for k in ["capacity", "capacity_low", "capacity_high"]:
            number(result[stream], k, 1, 10000, True)
        if not result[stream]["capacity_low"] <= result[stream]["capacity"] <= result[stream]["capacity_high"]:
            raise InputError(f"{stream.title()} capacity must be inside its supplied capacity range.")
    number(result["garbage"], "kg_per_pickup", .01, 500, nullable=True)
    number(result["garbage"], "payload_tonnes", .1, 100)
    for k in ["collection_access", "collection_side", "pickups_per_address_per_stream", "preserve_planning_sections", "allow_shared_overlong_sections", "final_unload_required", "loads_per_truck","objective"]:
        if result[k] != DEFAULTS[k]:
            raise InputError(f"This routing version requires {k.replace('_', ' ')} = {DEFAULTS[k]}.")
    return result
