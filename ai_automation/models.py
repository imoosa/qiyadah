"""Additive platform tables; every tenant-owned row carries company_id.

Separate metadata prevents the legacy application's automatic create_all paths
from deploying automation tables. Run the explicit migration command instead.
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON, UniqueConstraint, Numeric
from sqlalchemy.orm import declarative_base, synonym

Base = declarative_base()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def uid():
    return uuid4().hex


class TenantRow:
    id = Column(String(32), primary_key=True, default=uid)
    company_id = Column(String(50), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=now)


class CompanySettings(TenantRow, Base):
    __tablename__ = 'ai_company_settings'
    __table_args__ = (UniqueConstraint('company_id'),)
    enabled = Column(Boolean, nullable=False, default=False)
    app_type = Column(String(20), nullable=False, default='erp')
    plan_code = Column(String(30), nullable=False, default='standard')
    timezone = Column(String(80), nullable=False, default='Asia/Kolkata')
    daily_requests = Column(Integer, nullable=False, default=100)
    daily_messages = Column(Integer, nullable=False, default=50)
    daily_limit = synonym('daily_messages')
    monthly_limit = Column(Integer, nullable=False, default=1500)
    work_start = Column(Integer, nullable=False, default=9)
    work_end = Column(Integer, nullable=False, default=18)


class AgentConfig(TenantRow, Base):
    __tablename__ = 'ai_agent_configs'
    __table_args__ = (UniqueConstraint('company_id', 'kind'),)
    kind = Column(String(30), nullable=False)
    agent = synonym('kind')
    enabled = Column(Boolean, nullable=False, default=False)
    config = Column(JSON, nullable=False, default=dict)


class Conversation(TenantRow, Base):
    __tablename__ = 'ai_conversations'
    actor = Column(String(255), nullable=False)
    channel = Column(String(30), nullable=False, default='erp')
    contact = Column(String(255))
    external_ref = synonym('contact')
    lead_id = Column(String(50))
    crm_lead_id = synonym('lead_id')
    takeover = Column(Boolean, nullable=False, default=False)
    human_takeover = synonym('takeover')
    status = Column(String(30), nullable=False, default='open')
    agent = Column(String(30), nullable=False, default='knowledge')


class Message(TenantRow, Base):
    __tablename__ = 'ai_messages'
    conversation_id = Column(String(32), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=False, default=list)
    feedback = Column(String(10))


class AutomationRule(TenantRow, Base):
    __tablename__ = 'ai_automation_rules'
    name = Column(String(150), nullable=False)
    kind = Column(String(40), nullable=False)
    actor = Column(String(255), nullable=False, default='system')
    enabled = Column(Boolean, nullable=False, default=False)
    approval_required = Column(Boolean, nullable=False, default=True)
    config = Column(JSON, nullable=False, default=dict)
    next_run = Column(DateTime, nullable=False, default=now)


class AutomationRun(TenantRow, Base):
    __tablename__ = 'ai_automation_runs'
    __table_args__ = (UniqueConstraint('company_id', 'event_key'),)
    event_key = Column(String(64), nullable=False)
    kind = Column(String(40), nullable=False)
    actor = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default='pending')
    payload = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=False, default=dict)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, nullable=False, default=now)
    scheduled_for = synonym('available_at')
    claimed_at = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, default=now)
    error = Column(String(500))
    last_error = synonym('error')


class MessageQueue(TenantRow, Base):
    __tablename__ = 'ai_message_queue'
    __table_args__ = (UniqueConstraint('company_id', 'event_key'),)
    event_key = Column(String(64), nullable=False)
    actor = Column(String(255), nullable=False)
    channel = Column(String(20), nullable=False)
    recipient = Column(String(255), nullable=False)
    kind = Column(String(40), nullable=False)
    reference = Column(String(80))
    template = Column(String(150))
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(30), nullable=False, default='approval')
    approved_by = Column(String(255))
    provider_id = Column(String(255), index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, nullable=False, default=now)
    scheduled_for = synonym('available_at')
    claimed_at = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, default=now)
    error = Column(String(500))
    last_error = synonym('error')


class ContactConsent(TenantRow, Base):
    __tablename__ = 'ai_contact_consent'
    __table_args__ = (UniqueConstraint('company_id', 'channel', 'contact'),)
    channel = Column(String(20), nullable=False)
    contact = Column(String(255), nullable=False)
    allowed = Column(Boolean, nullable=False, default=False)
    evidence = Column(Text, nullable=False, default='admin')
    source = synonym('evidence')
    updated_at = Column(DateTime, nullable=False, default=now)


class KnowledgeSource(TenantRow, Base):
    __tablename__ = 'ai_knowledge_sources'
    title = Column(String(200), nullable=False)
    audience = Column(String(20), nullable=False, default='staff')
    application = Column(String(20), nullable=False, default='erp')
    filename = Column(String(255), default='document.txt')
    content = Column(Text, nullable=False)
    chunks = Column(JSON, nullable=False, default=list)
    active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, nullable=False, default=now)


class Integration(TenantRow, Base):
    __tablename__ = 'ai_integrations'
    __table_args__ = (UniqueConstraint('company_id', 'kind'),)
    kind = Column(String(30), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    active = synonym('enabled')
    config = Column(JSON, nullable=False, default=dict)
    encrypted_secrets = Column(Text)


class AuditLog(TenantRow, Base):
    __tablename__ = 'ai_audit_logs'
    actor = Column(String(255), nullable=False)
    action = Column(String(80), nullable=False)
    reference = Column(String(100))
    details = Column(JSON, nullable=False, default=dict)


class Usage(TenantRow, Base):
    __tablename__ = 'ai_usage'
    __table_args__ = (UniqueConstraint('company_id', 'bucket', 'kind'),)
    bucket = Column(String(30), nullable=False)
    kind = Column(String(30), nullable=False)
    count = Column(Integer, nullable=False, default=0)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost = Column(Numeric(18, 8), nullable=False, default=0)


class Appointment(TenantRow, Base):
    __tablename__ = 'ai_appointments'
    __table_args__ = (UniqueConstraint('company_id', 'event_key'),)
    event_key = Column(String(64), nullable=False)
    actor = Column(String(255), nullable=False)
    lead_id = Column(String(50), nullable=False)
    start = Column(DateTime, nullable=False)
    end = Column(DateTime, nullable=False)
    provider_id = Column(String(255))
    status = Column(String(30), nullable=False, default='reserved')


class BriefingReport(TenantRow, Base):
    __tablename__ = 'ai_briefing_reports'
    app_type = Column(String(20), nullable=False, default='erp')
    period_type = Column(String(20), nullable=False, default='daily')
    period_start = Column(String(20), nullable=False)
    period_end = Column(String(20), nullable=False)
    timezone = Column(String(50), nullable=False, default='Asia/Kolkata')
    metrics = Column(JSON, nullable=False, default=dict)
    explanation = Column(Text)
    sources = Column(JSON, nullable=False, default=dict)
    channels = Column(JSON, nullable=False, default=list)
    delivery_log = Column(JSON, nullable=False, default=dict)
    generated_by = Column(String(255))
