"""Shared constants for the component lifecycle."""
from . import models as m

STATUS_ORDER = [m.ORDERED, m.RECEIVED, m.INSPECTION_PENDING, m.IN_INSPECTION,
                m.APPROVED, m.IN_WAREHOUSE, m.IN_ASSEMBLY_BAY, m.INSTALLED]

EVENT_NAME = {
    m.ORDERED: "COMPONENT_ORDERED",
    m.RECEIVED: "COMPONENT_RECEIVED",
    m.INSPECTION_PENDING: "INSPECTION_QUEUED",
    m.IN_INSPECTION: "INSPECTION_STARTED",
    m.APPROVED: "COMPONENT_APPROVED",
    m.IN_WAREHOUSE: "MOVED_TO_WAREHOUSE",
    m.IN_ASSEMBLY_BAY: "MOVED_TO_ASSEMBLY_BAY",
    m.INSTALLED: "COMPONENT_INSTALLED",
    m.REJECTED: "COMPONENT_REJECTED",
}

LOCATION = {
    m.ORDERED: "In transit (supplier)",
    m.RECEIVED: "Receiving Dock",
    m.INSPECTION_PENDING: "Inspection Queue",
    m.IN_INSPECTION: "Inspection Lab",
    m.APPROVED: "Quality-Cleared Area",
    m.IN_WAREHOUSE: "Central Warehouse",
    m.IN_ASSEMBLY_BAY: "Assembly Bay",
    m.INSTALLED: "Installed on vehicle",
    m.REJECTED: "Quarantine",
}

INSPECTION_HOURS = 8   # time from arrival to usable (queue + inspection + clearance)

# dashboard groupings
GROUP_OF = {
    m.APPROVED: "available", m.IN_WAREHOUSE: "available",
    m.RECEIVED: "in_inspection", m.INSPECTION_PENDING: "in_inspection", m.IN_INSPECTION: "in_inspection",
    m.IN_ASSEMBLY_BAY: "in_assembly", m.INSTALLED: "installed",
    m.REJECTED: "rejected", m.ORDERED: "on_order",
}
