"""Booking-code job state machine. A code exists only with a confirmation id."""
from dataclasses import dataclass, field
ORDER = ["submitted", "resolved", "mapped", "previewed", "confirmed", "created"]

class ManualIntegration:
    supports_create = False
    def create_code(self, selections): return None  # unsupported: no fabricated code

@dataclass
class Job:
    status: str = "submitted"
    reason: str | None = None
    code: str | None = None
    per_selection: dict = field(default_factory=dict)

def advance(job: Job, to: str) -> Job:
    if job.status == "failed" or to not in ORDER or ORDER.index(to) != ORDER.index(job.status) + 1:
        raise ValueError(f"illegal transition {job.status} -> {to}")
    job.status = to; return job

def create(job: Job, integration, selections) -> Job:
    if job.status != "confirmed": raise ValueError("job must be confirmed first")
    conf = integration.create_code(selections) if integration.supports_create else None
    if conf and conf.get("confirmation_id") and conf.get("code"):
        job.code = conf["code"]; job.status = "created"
    else:
        job.status = "failed"
        job.reason = "integration returned no confirmation identifier" if integration.supports_create \
            else "this bookmaker has no authorised integration; enter selections manually or export"
    return job
