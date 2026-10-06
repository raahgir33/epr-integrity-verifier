"""Flat Pydantic extraction schemas, one per document type (docs/DATA_SPEC.md
§3). Every value is extracted exactly as printed (strings) — all parsing,
unit conversion and arithmetic happen in units.py (T7), never here or in the
model. Field names match what scripts/dossier_gen/shipments.py generates, so
ground-truth comparison in app/eval/evaluate.py needs no translation.

Schemas stay flat and simple: strings, no dict[str, X], no unions other
than Optional, no recursive models. Per-field confidence is a list of
objects, not a dict.
"""

from pydantic import BaseModel


class FieldConfidence(BaseModel):
    field: str
    confidence: float
    page: int


class CtoFacts(BaseModel):
    consent_no: str
    processor_name: str
    address: str
    permitted_categories: str
    capacity_t_per_year: str
    valid_from: str
    valid_to: str
    field_confidence: list[FieldConfidence]


class EprRegistrationFacts(BaseModel):
    registration_no: str
    processor_type: str
    categories: str
    capacity_t_per_year: str
    field_confidence: list[FieldConfidence]


class InboundInvoiceFacts(BaseModel):
    invoice_no: str
    date: str
    supplier_gstin: str
    buyer_gstin: str
    item_description: str
    hsn: str
    quantity_t: str
    rate: str
    value: str
    field_confidence: list[FieldConfidence]


class EwayBillFacts(BaseModel):
    ewb_no: str
    generated_at: str
    valid_until: str
    from_gstin: str
    to_gstin: str
    from_pin: str
    to_pin: str
    distance_km: str
    vehicle_no: str
    hsn: str
    quantity_t: str
    value: str
    invoice_no: str
    field_confidence: list[FieldConfidence]


class WeighbridgeSlipFacts(BaseModel):
    ticket_no: str
    vehicle_no: str
    gross_kg: str
    tare_kg: str
    net_kg: str
    in_time: str
    out_time: str
    remarks: str
    field_confidence: list[FieldConfidence]


class OutboundInvoiceFacts(BaseModel):
    invoice_no: str
    date: str
    buyer: str
    item_description: str
    hsn: str
    quantity_t: str
    field_confidence: list[FieldConfidence]


class ElectricityBillFacts(BaseModel):
    billing_month: str
    units_consumed_kwh: str
    connected_load_kw: str
    field_confidence: list[FieldConfidence]


SCHEMA_BY_DOC_TYPE: dict[str, type[BaseModel]] = {
    "cto": CtoFacts,
    "epr_registration": EprRegistrationFacts,
    "inbound_invoice": InboundInvoiceFacts,
    "eway_bill": EwayBillFacts,
    "weighbridge_slip": WeighbridgeSlipFacts,
    "outbound_invoice": OutboundInvoiceFacts,
    "electricity_bill": ElectricityBillFacts,
}
