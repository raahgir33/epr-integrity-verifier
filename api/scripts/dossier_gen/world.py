"""Fixed world definition: the 10 processors (with their F1-F8/H1-H4
assignment), 25 suppliers and 3 brands. All entities are fictional.
See docs/DATA_SPEC.md §2 and §5 for the rules this encodes.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from scripts.dossier_gen.gstin import generate_invalid_gstin

REPO_ROOT = Path(__file__).resolve().parents[3]
SITE_COORDINATES_PATH = REPO_ROOT / "data" / "synthetic" / "site_coordinates.json"


@dataclass(frozen=True)
class Processor:
    processor_id: str
    name: str
    type: str  # "recycler" | "end_of_life"
    permitted_categories: list[str]
    capacity_t_per_year: float
    consent_no: str
    consent_valid_from: str  # DD/MM/YYYY, as printed
    consent_valid_to: str
    registration_no: str
    gstin: str
    address: str
    pin_code: str
    state: str
    weighbridge_code: str
    invoice_prefix: str
    lat: float
    lon: float
    site_validated: bool
    site_note: str
    issue_types: list[str] = field(default_factory=list)
    hard_negatives: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    name: str
    gstin: str
    pin_code: str
    invoice_prefix: str
    lat: float
    lon: float
    city: str
    state: str


@dataclass(frozen=True)
class Brand:
    brand_id: str
    name: str


# processor_id -> (name, type, permitted_categories, capacity_t_per_year,
#                  issue_types, hard_negatives)
# This is the fixed assignment from docs/DATA_SPEC.md §5.
_PROCESSOR_CATALOG = [
    ("PWP-01", "Sahyadri Green Recyclers Pvt. Ltd.", "recycler", ["I", "II"], 6000, [], []),
    ("PWP-02", "Sabarmati Polymer Recovery Pvt. Ltd.", "recycler", ["I", "II"], 7200, [], []),
    (
        "PWP-03",
        "Vishwamitri Plastics Recycling Co.",
        "recycler",
        ["I", "II"],
        5400,
        [],
        ["H1", "H2"],
    ),
    ("PWP-04", "Palar Valley Recyclers Pvt. Ltd.", "recycler", ["I", "II"], 8000, [], ["H3", "H4"]),
    ("PWP-05", "Ponnaiyar Polymer Works", "recycler", ["I", "II"], 4800, ["F1", "F8"], []),
    ("PWP-06", "Manjira Recycling Industries", "recycler", ["I", "II"], 5200, ["F1", "F3"], []),
    (
        "PWP-07",
        "Narmada Valley Plastics Pvt. Ltd.",
        "recycler",
        ["I", "II"],
        6600,
        ["F2", "F7"],
        [],
    ),
    ("PWP-08", "Yamuna Belt Recyclers Pvt. Ltd.", "recycler", ["I", "II"], 5000, ["F8"], []),
    (
        "PWP-09",
        "Aravalli EcoProcessors Pvt. Ltd.",
        "end_of_life",
        ["III", "IV"],
        20000,
        ["F5", "F6"],
        [],
    ),
    (
        "PWP-10",
        "Kanhan River Processors Pvt. Ltd.",
        "end_of_life",
        ["III", "IV"],
        18000,
        ["F4"],
        [],
    ),
]

_STATE_FOR_PROCESSOR = {
    "PWP-01": "Maharashtra",
    "PWP-02": "Gujarat",
    "PWP-03": "Gujarat",
    "PWP-04": "Tamil Nadu",
    "PWP-05": "Tamil Nadu",
    "PWP-06": "Telangana",
    "PWP-07": "Madhya Pradesh",
    "PWP-08": "Haryana",
    "PWP-09": "Rajasthan",
    "PWP-10": "Maharashtra",
}

# Which anchor city (see _SUPPLIER_ANCHORS below) each processor's PIN
# code is consistent with — not arbitrary: matches the city already named
# in each processor's data/synthetic/site_coordinates.json "note" field
# (PWP-04/06/07/09 use the nearest anchor to their real coordinates, the
# rest are exact matches).
_CITY_FOR_PROCESSOR = {
    "PWP-01": "Pune",
    "PWP-02": "Ahmedabad",
    "PWP-03": "Vadodara",
    "PWP-04": "Chennai",
    "PWP-05": "Hosur",
    "PWP-06": "Hyderabad",
    "PWP-07": "Indore",
    "PWP-08": "Faridabad",
    "PWP-09": "Alwar",
    "PWP-10": "Nagpur",
}

# Real GST state codes (public information) for every state in play —
# the 7 processor states plus Delhi and Uttar Pradesh (supplier-anchor
# states with no processor). Used so a fictional GSTIN's state code
# matches the entity's actual state, not an independently-random one.
STATE_GSTIN_CODE = {
    "Maharashtra": "27",
    "Gujarat": "24",
    "Tamil Nadu": "33",
    "Telangana": "36",
    "Madhya Pradesh": "23",
    "Haryana": "06",
    "Rajasthan": "08",
    "Delhi": "07",
    "Uttar Pradesh": "09",
}

# Real India Post PIN prefixes (first 3 digits) for every anchor city —
# web-search-verified public information (bankbazaar.com / indiatvnews.com
# city PIN-code pages), not guessed. Used so a fictional PIN code's prefix
# matches the entity's actual city.
PIN_PREFIX = {
    "Pune": "411",
    "Mumbai": "400",
    "Nashik": "422",
    "Nagpur": "440",
    "Ahmedabad": "380",
    "Surat": "395",
    "Vadodara": "390",
    "Rajkot": "360",
    "Chennai": "600",
    "Coimbatore": "641",
    "Madurai": "625",
    "Hosur": "635",
    "Hyderabad": "500",
    "Warangal": "506",
    "Indore": "452",
    "Bhopal": "462",
    "Gwalior": "474",
    "Faridabad": "121",
    "Gurugram": "122",
    "Panchkula": "134",
    "Jaipur": "302",
    "Alwar": "301",
    "Kota": "324",
    "Delhi": "110",
    "Kanpur": "208",
}

# T10 realism fix (docs/PROGRESS.md): a single global scale applied to
# every processor's capacity_t_per_year, so FY inbound tonnage divides
# into realistic single-vehicle-trip shipments (app/checks/params.py's
# vehicle classes, see shipments.py) instead of the pre-fix ~260-1,370 t
# per shipment. Certificates/outputs/energy all auto-scale through their
# existing formulas (derived from capacity_t_per_year or actual shipment
# totals) — this is the only place the scale itself is applied.
# Tuned empirically (tests/test_generator_realism.py, all 20 dev seeds)
# against the vehicle-class net ranges and the 15-35 shipment-count band
# in shipments.py — not independently meaningful on its own.
WORLD_SCALE_FACTOR = 0.032

# 25 fictional aggregators across nearby states, one per anchor city.
# (city, state, approx lat, approx lon) — city-centre level, not addresses.
_SUPPLIER_ANCHORS = [
    ("Pune", "Maharashtra", 18.5204, 73.8567),
    ("Mumbai", "Maharashtra", 19.0760, 72.8777),
    ("Nashik", "Maharashtra", 19.9975, 73.7898),
    ("Nagpur", "Maharashtra", 21.1458, 79.0882),
    ("Ahmedabad", "Gujarat", 23.0225, 72.5714),
    ("Surat", "Gujarat", 21.1702, 72.8311),
    ("Vadodara", "Gujarat", 22.3072, 73.1812),
    ("Rajkot", "Gujarat", 22.3039, 70.8022),
    ("Chennai", "Tamil Nadu", 13.0827, 80.2707),
    ("Coimbatore", "Tamil Nadu", 11.0168, 76.9558),
    ("Madurai", "Tamil Nadu", 9.9252, 78.1198),
    ("Hosur", "Tamil Nadu", 12.7409, 77.8253),
    ("Hyderabad", "Telangana", 17.3850, 78.4867),
    ("Warangal", "Telangana", 17.9784, 79.5941),
    ("Indore", "Madhya Pradesh", 22.7196, 75.8577),
    ("Bhopal", "Madhya Pradesh", 23.2599, 77.4126),
    ("Gwalior", "Madhya Pradesh", 26.2183, 78.1828),
    ("Faridabad", "Haryana", 28.4089, 77.3178),
    ("Gurugram", "Haryana", 28.4595, 77.0266),
    ("Panchkula", "Haryana", 30.6942, 76.8606),
    ("Jaipur", "Rajasthan", 26.9124, 75.7873),
    ("Alwar", "Rajasthan", 27.5530, 76.6346),
    ("Kota", "Rajasthan", 25.2138, 75.8648),
    ("Delhi", "Delhi", 28.7041, 77.1025),
    ("Kanpur", "Uttar Pradesh", 26.4499, 80.3319),
]

_BRAND_CATALOG = [
    ("BRAND-01", "Himalaya FreshFoods Ltd."),
    ("BRAND-02", "Konkan Beverages Pvt. Ltd."),
    ("BRAND-03", "Deccan Home Care Products Ltd."),
]


# 2-letter vehicle-registration-style state codes — same abbreviations
# shipments.py already draws vehicle_no prefixes from, reused here so
# consent/registration/weighbridge references look like the same
# jurisdiction's documents.
_STATE_ABBR = {
    "Maharashtra": "MH",
    "Gujarat": "GJ",
    "Tamil Nadu": "TN",
    "Telangana": "TG",
    "Madhya Pradesh": "MP",
    "Haryana": "HR",
    "Rajasthan": "RJ",
}


def _initials(name: str) -> str:
    return "".join(word[0] for word in name.split() if word and word[0].isalpha()).upper()


def _unique_prefix(name: str, seen: dict[str, int]) -> str:
    """T10 realism fix (docs/PROGRESS.md): a business-name-derived series
    prefix, never the internal catalog id (PWP-xx/SUP-xx). Two names can
    share initials (e.g. two "W..." cities with the same supplier-name
    suffix) — disambiguated with a small numeric suffix on repeats,
    checked rather than assumed collision-free."""
    base = _initials(name)
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}{seen[base]}"


def load_site_coordinates() -> dict:
    with SITE_COORDINATES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def build_processors(rng: random.Random) -> list[Processor]:
    sites = load_site_coordinates()
    processors = []
    seen_prefixes: dict[str, int] = {}
    for pid, name, ptype, categories, capacity, issues, hard_negs in _PROCESSOR_CATALOG:
        site = sites[pid]
        state = _STATE_FOR_PROCESSOR[pid]
        city = _CITY_FOR_PROCESSOR[pid]
        abbr = _STATE_ABBR[state]
        processors.append(
            Processor(
                processor_id=pid,
                name=name,
                type=ptype,
                permitted_categories=categories,
                capacity_t_per_year=float(capacity) * WORLD_SCALE_FACTOR,
                consent_no=f"CTO/{abbr}/{rng.randint(100000, 999999)}",
                consent_valid_from="01/04/2022",
                consent_valid_to="31/03/2028",
                registration_no=f"EPR-REG/{abbr}/{rng.randint(100000, 999999)}",
                gstin=generate_invalid_gstin(rng, state_code=STATE_GSTIN_CODE[state]),
                address=f"Plot {rng.randint(1, 200)}, Industrial Area, {state}",
                pin_code=f"{PIN_PREFIX[city]}{rng.randint(100, 999)}",
                state=state,
                weighbridge_code=f"{abbr}-WB-{rng.randint(1000, 9999)}",
                invoice_prefix=_unique_prefix(name, seen_prefixes),
                lat=site["lat"],
                lon=site["lon"],
                site_validated=site["site_validated"],
                site_note=site["note"],
                issue_types=list(issues),
                hard_negatives=list(hard_negs),
            )
        )
    return processors


def build_suppliers(rng: random.Random) -> list[Supplier]:
    suppliers = []
    name_suffixes = ["Waste Aggregators", "Scrap Traders", "Recyclables Pvt. Ltd.", "Enterprises"]
    seen_prefixes: dict[str, int] = {}
    for i, (city, state, lat, lon) in enumerate(_SUPPLIER_ANCHORS, start=1):
        supplier_id = f"SUP-{i:02d}"
        suffix = name_suffixes[i % len(name_suffixes)]
        name = f"{city} {suffix}"
        suppliers.append(
            Supplier(
                supplier_id=supplier_id,
                name=name,
                gstin=generate_invalid_gstin(rng, state_code=STATE_GSTIN_CODE[state]),
                pin_code=f"{PIN_PREFIX[city]}{rng.randint(100, 999)}",
                invoice_prefix=_unique_prefix(name, seen_prefixes),
                lat=round(lat + rng.uniform(-0.15, 0.15), 4),
                lon=round(lon + rng.uniform(-0.15, 0.15), 4),
                city=city,
                state=state,
            )
        )
    return suppliers


def build_brands() -> list[Brand]:
    return [Brand(brand_id=bid, name=name) for bid, name in _BRAND_CATALOG]
