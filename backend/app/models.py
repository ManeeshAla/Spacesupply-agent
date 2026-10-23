"""Database schema. All simulated times are integer 'hours since project start'."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# ---- Component lifecycle -------------------------------------------------
ORDERED = "ORDERED"
RECEIVED = "RECEIVED"
INSPECTION_PENDING = "INSPECTION_PENDING"
IN_INSPECTION = "IN_INSPECTION"
APPROVED = "APPROVED"
IN_WAREHOUSE = "IN_WAREHOUSE"
IN_ASSEMBLY_BAY = "IN_ASSEMBLY_BAY"
INSTALLED = "INSTALLED"
REJECTED = "REJECTED"

# statuses in which a component can be used by a task right now
USABLE = {APPROVED, IN_WAREHOUSE, IN_ASSEMBLY_BAY, INSTALLED}

ALLOWED_TRANSITIONS = {
    ORDERED: {RECEIVED},
    RECEIVED: {INSPECTION_PENDING},
    INSPECTION_PENDING: {IN_INSPECTION},
    IN_INSPECTION: {APPROVED, REJECTED},
    APPROVED: {IN_WAREHOUSE},
    IN_WAREHOUSE: {IN_ASSEMBLY_BAY},
    IN_ASSEMBLY_BAY: {INSTALLED},
    INSTALLED: set(),
    REJECTED: {ORDERED, RECEIVED},  # replacement ordered / received
}

# ---- Task statuses -------------------------------------------------------
T_PENDING = "PENDING"
T_IN_PROGRESS = "IN_PROGRESS"
T_COMPLETED = "COMPLETED"


class SimState(Base):
    __tablename__ = "sim_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    now_hour: Mapped[int] = mapped_column(Integer, default=0)
    start_iso: Mapped[str] = mapped_column(String(40))


class Stage(Base):
    __tablename__ = "stages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    short_name: Mapped[str] = mapped_column(String(40))


class Workstation(Base):
    __tablename__ = "workstations"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    ws_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")  # AVAILABLE | DOWN
    available_from: Mapped[int] = mapped_column(Integer, default=0)       # hour when it is free again
    maintenance_due_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    reliability: Mapped[float] = mapped_column(Float, default=0.9)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)


class Component(Base):
    __tablename__ = "components"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)  # CMP-001
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40))
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"))
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)           # units in this lot
    required_quantity: Mapped[int] = mapped_column(Integer, default=1)  # total still needed by pending tasks
    status: Mapped[str] = mapped_column(String(24), default=ORDERED)
    location: Mapped[str] = mapped_column(String(60), default="Supplier")
    inspection_status: Mapped[str] = mapped_column(String(16), default="PENDING")
    criticality: Mapped[str] = mapped_column(String(10), default="NORMAL")  # CRITICAL | HIGH | NORMAL
    expected_ready_hour: Mapped[int] = mapped_column(Integer, default=0)    # hour it becomes usable
    delay_hours: Mapped[int] = mapped_column(Integer, default=0)

    stage: Mapped[Stage] = relationship()
    supplier: Mapped[Supplier] = relationship()


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    component_id: Mapped[str] = mapped_column(ForeignKey("components.id"))
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    eta_hour: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="ON_TIME")  # ON_TIME | DELAYED | ARRIVED
    delay_hours: Mapped[int] = mapped_column(Integer, default=0)
    is_replacement: Mapped[bool] = mapped_column(Boolean, default=False)

    component: Mapped[Component] = relationship()
    supplier: Mapped[Supplier] = relationship()


class ComponentEvent(Base):
    __tablename__ = "component_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[str] = mapped_column(ForeignKey("components.id"), index=True)
    hour: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    location: Mapped[str | None] = mapped_column(String(60), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)  # T-001
    name: Mapped[str] = mapped_column(String(80))
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"))
    ws_type: Mapped[str] = mapped_column(String(20))
    duration: Mapped[int] = mapped_column(Integer)          # hours
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1 (low) .. 5 (highest)
    deadline_hour: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(14), default=T_PENDING)
    workstation_id: Mapped[str | None] = mapped_column(ForeignKey("workstations.id"), nullable=True)
    start_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)  # actual start (if started)
    end_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)    # actual / committed end

    stage: Mapped[Stage] = relationship()


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    depends_on_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)


class TaskRequirement(Base):
    __tablename__ = "task_requirements"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    component_id: Mapped[str] = mapped_column(ForeignKey("components.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)


class ScheduleVersion(Base):
    __tablename__ = "schedule_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_hour: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    algorithm: Mapped[str] = mapped_column(String(20))
    trigger: Mapped[str] = mapped_column(String(120), default="manual")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    workstation_id: Mapped[str] = mapped_column(ForeignKey("workstations.id"))
    start_hour: Mapped[int] = mapped_column(Integer)
    end_hour: Mapped[int] = mapped_column(Integer)
    reason_type: Mapped[str] = mapped_column(String(20), default="")   # COMPONENT | PREDECESSOR | WORKSTATION | OPTIMIZER | NOW
    reason_text: Mapped[str] = mapped_column(Text, default="")
    binding_ref: Mapped[str | None] = mapped_column(String(12), nullable=True)  # id of binding component/task/workstation


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedupe_key: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(10))  # CRITICAL | WARNING | INFO
    category: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text, default="")
    task_id: Mapped[str | None] = mapped_column(String(10), nullable=True)
    component_id: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_hour: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(12), default="OPEN")  # OPEN | ACKNOWLEDGED | RESOLVED


class AgentLog(Base):
    __tablename__ = "agent_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent: Mapped[str] = mapped_column(String(24))
    message: Mapped[str] = mapped_column(Text)
    hour: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentMessage(Base):
    """One structured message sent from one agent to another over the message bus (see bus.py)."""
    __tablename__ = "agent_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(32), index=True)       # supplier.delay | schedule.replanned | ...
    sender: Mapped[str] = mapped_column(String(24))
    recipient: Mapped[str] = mapped_column(String(24), default="*")  # "*" = broadcast
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)  # groups one conversation
    summary: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    hour: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
