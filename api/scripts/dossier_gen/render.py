"""Renders documents: Jinja2 HTML -> Playwright (Chromium) -> PDF for six
document types, and HTML -> screenshot -> seeded Pillow degradation -> PNG
for weighbridge slips. The Devanagari font is embedded as a base64
@font-face so rendering doesn't depend on fonts installed on the machine.

Runs only on the developer's machine, never on Cloud Run.
"""

import base64
import random
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageEnhance
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
FONT_PATH = REPO_ROOT / "assets" / "fonts" / "NotoSansDevanagari-Regular.ttf"

# field key -> {"en": ..., "hi": ...}, per document type.
LABELS: dict[str, dict[str, dict[str, str]]] = {
    "cto": {
        "consent_no": {"en": "Consent No.", "hi": "सहमति क्रमांक"},
        "processor_name": {"en": "Processor Name", "hi": "प्रोसेसर का नाम"},
        "address": {"en": "Address", "hi": "पता"},
        "permitted_categories": {"en": "Permitted Categories", "hi": "अनुमत श्रेणियाँ"},
        "capacity_t_per_year": {"en": "Capacity (t/yr)", "hi": "क्षमता (टन/वर्ष)"},
        "valid_from": {"en": "Valid From", "hi": "वैध से"},
        "valid_to": {"en": "Valid To", "hi": "वैध तक"},
    },
    "epr_registration": {
        "registration_no": {"en": "Registration No.", "hi": "पंजीकरण क्रमांक"},
        "processor_type": {"en": "Processor Type", "hi": "प्रोसेसर प्रकार"},
        "categories": {"en": "Categories", "hi": "श्रेणियाँ"},
        "capacity_t_per_year": {"en": "Capacity (t/yr)", "hi": "क्षमता (टन/वर्ष)"},
    },
    "inbound_invoice": {
        "invoice_no": {"en": "Invoice No.", "hi": "चालान क्रमांक"},
        "date": {"en": "Date", "hi": "तिथि"},
        "supplier_gstin": {"en": "Supplier GSTIN", "hi": "विक्रेता जीएसटीआईएन"},
        "buyer_gstin": {"en": "Buyer GSTIN", "hi": "खरीदार जीएसटीआईएन"},
        "item_description": {"en": "Item Description", "hi": "वस्तु विवरण"},
        "hsn": {"en": "HSN", "hi": "एचएसएन"},
        "quantity_t": {"en": "Quantity (t)", "hi": "मात्रा (टन)"},
        "rate": {"en": "Rate", "hi": "दर"},
        "value": {"en": "Value", "hi": "मूल्य"},
    },
    "eway_bill": {
        "ewb_no": {"en": "E-Way Bill No.", "hi": "ई-वे बिल क्रमांक"},
        "generated_at": {"en": "Generated At", "hi": "जनित समय"},
        "valid_until": {"en": "Valid Until", "hi": "वैधता तक"},
        "from_gstin": {"en": "From GSTIN", "hi": "प्रेषक जीएसटीआईएन"},
        "to_gstin": {"en": "To GSTIN", "hi": "प्राप्तकर्ता जीएसटीआईएन"},
        "from_pin": {"en": "From PIN", "hi": "प्रेषक पिन"},
        "to_pin": {"en": "To PIN", "hi": "प्राप्तकर्ता पिन"},
        "distance_km": {"en": "Distance (km)", "hi": "दूरी (किमी)"},
        "vehicle_no": {"en": "Vehicle No.", "hi": "वाहन क्रमांक"},
        "hsn": {"en": "HSN", "hi": "एचएसएन"},
        "quantity_t": {"en": "Quantity (t)", "hi": "मात्रा (टन)"},
        "value": {"en": "Value", "hi": "मूल्य"},
        "invoice_no": {"en": "Invoice No.", "hi": "चालान क्रमांक"},
    },
    "weighbridge_slip": {
        "ticket_no": {"en": "Ticket No.", "hi": "टिकट क्रमांक"},
        "vehicle_no": {"en": "Vehicle No.", "hi": "वाहन क्रमांक"},
        "gross_kg": {"en": "Gross (kg)", "hi": "सकल (किग्रा)"},
        "tare_kg": {"en": "Tare (kg)", "hi": "खाली वजन (किग्रा)"},
        "net_kg": {"en": "Net (kg)", "hi": "शुद्ध (किग्रा)"},
        "in_time": {"en": "In Time", "hi": "प्रवेश समय"},
        "out_time": {"en": "Out Time", "hi": "निकासी समय"},
        "remarks": {"en": "Remarks", "hi": "टिप्पणी"},
    },
    "outbound_invoice": {
        "invoice_no": {"en": "Invoice No.", "hi": "चालान क्रमांक"},
        "date": {"en": "Date", "hi": "तिथि"},
        "buyer": {"en": "Buyer", "hi": "खरीदार"},
        "item_description": {"en": "Item Description", "hi": "वस्तु विवरण"},
        "hsn": {"en": "HSN", "hi": "एचएसएन"},
        "quantity_t": {"en": "Quantity (t)", "hi": "मात्रा (टन)"},
    },
    "electricity_bill": {
        "billing_month": {"en": "Billing Month", "hi": "बिलिंग माह"},
        "units_consumed_kwh": {"en": "Units Consumed (kWh)", "hi": "उपभोग इकाइयाँ (kWh)"},
        "connected_load_kw": {"en": "Connected Load (kW)", "hi": "संयोजित भार (kW)"},
    },
}


def get_labels(doc_type: str, fields: dict, lang: str) -> dict[str, str]:
    doc_labels = LABELS[doc_type]
    return {key: doc_labels[key][lang] for key in fields}


def degrade_photo(path: Path, rng: random.Random) -> None:
    """Rotate slightly, add plausible sensor noise, and jitter brightness —
    every parameter drawn from the seeded `rng` — so a rendered PNG looks
    photographed rather than screenshotted."""
    image = Image.open(path).convert("RGB")

    angle = rng.uniform(-3, 3)
    image = image.rotate(angle, expand=True, fillcolor=(255, 255, 255))

    small_w, small_h = max(image.width // 8, 1), max(image.height // 8, 1)
    amplitude = rng.uniform(6, 16)
    noise_bytes = bytes(
        max(0, min(255, 128 + int(rng.uniform(-amplitude, amplitude))))
        for _ in range(small_w * small_h)
    )
    noise = Image.frombytes("L", (small_w, small_h), noise_bytes).resize(image.size, Image.BILINEAR)
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    image = Image.blend(image, noise_rgb, alpha=0.08)

    brightness_factor = rng.uniform(0.85, 1.1)
    image = ImageEnhance.Brightness(image).enhance(brightness_factor)

    image.save(path)


class Renderer:
    def __init__(self):
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
        )
        self.font_base64 = base64.b64encode(FONT_PATH.read_bytes()).decode("ascii")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()
        self._page = self._browser.new_page()

    def close(self) -> None:
        self._page.close()
        self._browser.close()
        self._playwright.stop()

    def __enter__(self) -> "Renderer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _render_html(self, doc_type: str, fields: dict, lang: str) -> str:
        template = self.env.get_template(f"{doc_type}.html")
        labels = get_labels(doc_type, fields, lang)
        return template.render(
            fields=fields, labels=labels, lang=lang, font_base64=self.font_base64
        )

    def render_pdf(self, doc_type: str, fields: dict, lang: str, output_path: Path) -> None:
        html = self._render_html(doc_type, fields, lang)
        self._page.set_content(html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._page.pdf(path=str(output_path), format="A4")

    def render_weighbridge_png(
        self, fields: dict, lang: str, output_path: Path, rng: random.Random
    ) -> None:
        html = self._render_html("weighbridge_slip", fields, lang)
        self._page.set_viewport_size({"width": 700, "height": 500})
        self._page.set_content(html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(output_path))
        degrade_photo(output_path, rng)
