"""CheckResult: the output of every function in app/checks/ and
app/checks/runner.py. Pure data, no I/O — see docs/DATA_SPEC.md §4a.
"""

from typing import Literal

from pydantic import BaseModel

CheckStatus = Literal["pass", "fail", "warn", "not_evaluable"]
CheckSeverity = Literal["hard", "soft"]


class CheckResult(BaseModel):
    check_id: str
    status: CheckStatus
    severity: CheckSeverity
    measured: float | None = None
    threshold: float | None = None
    affected_tonnes: float | None = None
    evidence_ids: list[str] = []
    explanation: str
