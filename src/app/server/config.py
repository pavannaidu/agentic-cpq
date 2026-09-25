from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _email_allowlist(name: str) -> frozenset[str]:
    return frozenset(
        value.strip().casefold()
        for value in os.environ.get(name, "").split(",")
        if value.strip()
    )


@dataclass(frozen=True)
class Settings:
    databricks_app_name: str
    agent_prefix: str
    use_mock_fallback: bool
    agent_model: str
    agent_timeout_seconds: int
    default_account_id: str
    followups_enabled: bool
    followup_endpoint: str
    plans_enabled: bool
    plan_confirmation_secret: str
    genie_enabled: bool
    genie_space_id: str | None
    manager_email_allowlist: frozenset[str]

    @property
    def environment(self) -> str:
        explicit = os.environ.get("AGENTIC_CPQ_ENVIRONMENT")
        if explicit:
            return explicit
        app_name = self.databricks_app_name.lower()
        for candidate in ("prod", "staging", "dev"):
            if app_name.endswith(f"-{candidate}"):
                return candidate
        return "dev"

    @property
    def is_databricks_app(self) -> bool:
        return bool(os.environ.get("DATABRICKS_APP_NAME"))

    @property
    def quote_agent_name(self) -> str:
        return "AgenticCPQAgent"

    @property
    def genie_space_title(self) -> str:
        return f"{self.agent_prefix}-genie-{self.environment}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        databricks_app_name=os.environ.get("DATABRICKS_APP_NAME", "agentic-cpq-seller-demo-dev"),
        agent_prefix=os.environ.get("AGENTIC_CPQ_AGENT_PREFIX", "agentic-cpq"),
        use_mock_fallback=_as_bool(os.environ.get("AGENTIC_CPQ_USE_MOCK_FALLBACK"), False),
        agent_model=os.environ.get("AGENTIC_CPQ_AGENT_MODEL", "databricks-gpt-5-6-terra"),
        agent_timeout_seconds=int(os.environ.get("AGENTIC_CPQ_AGENT_TIMEOUT_SECONDS", "110")),
        default_account_id=os.environ.get("AGENTIC_CPQ_DEFAULT_ACCOUNT_ID", "acct-riverfront"),
        followups_enabled=_as_bool(os.environ.get("AGENTIC_CPQ_FOLLOWUPS_ENABLED"), True),
        followup_endpoint=os.environ.get("AGENTIC_CPQ_FOLLOWUP_ENDPOINT", "databricks-gpt-5-6-luna"),
        plans_enabled=_as_bool(os.environ.get("AGENTIC_CPQ_PLANS_ENABLED"), False),
        # Local development and tests may omit this and use a process-private
        # fallback. A deployed app with plans enabled fails closed unless the
        # stable secret resource is injected.
        plan_confirmation_secret=os.environ.get("AGENTIC_CPQ_PLAN_CONFIRMATION_SECRET", ""),
        genie_enabled=_as_bool(os.environ.get("AGENTIC_CPQ_GENIE_ENABLED"), True),
        genie_space_id=os.environ.get("AGENTIC_CPQ_GENIE_SPACE_ID"),
        manager_email_allowlist=_email_allowlist("AGENTIC_CPQ_MANAGER_EMAILS"),
    )
