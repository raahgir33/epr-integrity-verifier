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
    lat: float
    lon: float


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


def load_site_coordinates() -> dict:
    with SITE_COORDINATES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def build_processors(rng: random.Random) -> list[Processor]:
    sites = load_site_coordinates()
    processors = []
    for pid, name, ptype, categories, capacity, issues, hard_negs in _PROCESSOR_CATALOG:
        site = sites[pid]
        state = _STATE_FOR_PROCESSOR[pid]
        processors.append(
            Processor(
                processor_id=pid,
                name=name,
                type=ptype,
                permitted_categories=categories,
                capacity_t_per_year=float(capacity),
                consent_no=f"CTO-{pid}-{rng.randint(10000, 99999)}",
                consent_valid_from="01/04/2022",
                consent_valid_to="31/03/2028",
                registration_no=f"EPR-REG-{pid}-{rng.randint(1000, 9999)}",
                gstin=generate_invalid_gstin(rng),
                address=f"Plot {rng.randint(1, 200)}, Industrial Area, {state}",
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
    for i, (city, _state, lat, lon) in enumerate(_SUPPLIER_ANCHORS, start=1):
        supplier_id = f"SUP-{i:02d}"
        suffix = name_suffixes[i % len(name_suffixes)]
        suppliers.append(
            Supplier(
                supplier_id=supplier_id,
                name=f"{city} {suffix}",
                gstin=generate_invalid_gstin(rng),
                pin_code=f"{rng.randint(100000, 899999)}",
                lat=round(lat + rng.uniform(-0.15, 0.15), 4),
                lon=round(lon + rng.uniform(-0.15, 0.15), 4),
            )
        )
    return suppliers


def build_brands() -> list[Brand]:
    return [Brand(brand_id=bid, name=name) for bid, name in _BRAND_CATALOG]
