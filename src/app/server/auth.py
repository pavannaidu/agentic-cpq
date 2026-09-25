from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from .config import Settings


LOCAL_ACTOR_EMAIL = "local-seller@example.invalid"


@dataclass(frozen=True, slots=True)
class ActorContext:
    """Authenticated browser identity and its server-authorized presentation views.

    Databricks Apps authenticate workspace calls as the App service principal while forwarding
    the signed-in user in trusted proxy headers.  The former is the execution identity; the latter
    owns the draft and determines whether buy-side manager fields may be rendered.
    """

    email: str
    username: str
    authenticated: bool
    allowed_views: tuple[str, ...]
    execution_identity: str

    @property
    def can_manage(self) -> bool:
        return "manager" in self.allowed_views

    def authorize_view(self, requested: str | None) -> str:
        view = (requested or "seller").strip().lower()
        if view == "demo":
            view = "manager"
        if view not in {"seller", "manager"}:
            view = "seller"
        if view not in self.allowed_views:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The signed-in user is not authorized for the requested view.",
            )
        return view


def _forwarded_value(request: Request, *names: str) -> str:
    for name in names:
        value = request.headers.get(name)
        if value and value.strip():
            return value.strip()
    return ""


def actor_from_request(request: Request, settings: Settings) -> ActorContext:
    email = _forwarded_value(request, "x-forwarded-email", "x-forwarded-user")
    username = _forwarded_value(
        request,
        "x-forwarded-preferred-username",
        "x-forwarded-user",
    )
    authenticated = bool(email or username)

    if settings.is_databricks_app and not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A signed-in Databricks Apps user is required.",
        )

    # An unauthenticated identity is possible only in local development.  It is deliberately a
    # named, auditable actor rather than an empty owner.  Deployed Apps never grant manager access
    # merely because a client asks for it; that requires the server-side email allowlist.
    actor_email = (email or LOCAL_ACTOR_EMAIL).casefold()
    is_local = not settings.is_databricks_app and not authenticated
    manager_allowed = is_local or actor_email in settings.manager_email_allowlist
    allowed = ("seller", "manager") if manager_allowed else ("seller",)
    execution_identity = (
        f"databricks-app:{settings.databricks_app_name}"
        if settings.is_databricks_app
        else "local-databricks-profile"
    )
    return ActorContext(
        email=actor_email,
        username=username or email or "local dev",
        authenticated=authenticated,
        allowed_views=allowed,
        execution_identity=execution_identity,
    )
