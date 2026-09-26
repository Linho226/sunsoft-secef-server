from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from sunsoft_secef_server.admin.security import (
    ensure_csrf_token,
    is_admin_authenticated,
    verify_csrf_token,
    verify_password,
)
from sunsoft_secef_server.api.dependencies import (
    SessionDependency,
)
from sunsoft_secef_server.config import Settings
from sunsoft_secef_server.storage.auth_repositories import (
    ActivationCodeError,
    AgentActivationCodeRepository,
    AuthRepositoryError,
    SiteRepository,
    TenantRepository,
)
from sunsoft_secef_server.storage.release_repositories import (
    AgentReleaseRepository,
    AgentReleaseRepositoryError,
)
from sunsoft_secef_server.storage.models import (
    Agent,
    AgentActivationCode,
    Site,
    Tenant,
    utc_now,
)


PACKAGE_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

templates = Jinja2Templates(
    directory=str(
        PACKAGE_ROOT / "templates"
    )
)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    include_in_schema=False,
)


def _settings(
    request: Request,
) -> Settings:
    settings = getattr(
        request.app.state,
        "settings",
        None,
    )

    if settings is None:
        raise RuntimeError(
            "Configuration serveur indisponible."
        )

    return settings


def _ensure_enabled(
    request: Request,
) -> Settings:
    settings = _settings(
        request
    )

    if not settings.admin_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )

    return settings


def _login_redirect() -> RedirectResponse:
    return RedirectResponse(
        url="/admin/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _require_admin(
    request: Request,
) -> RedirectResponse | None:
    _ensure_enabled(
        request
    )

    if not is_admin_authenticated(
        request
    ):
        return _login_redirect()

    return None


def _fmt_datetime(
    value: datetime | None,
) -> str:
    if value is None:
        return "—"

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    value = value.astimezone(
        timezone.utc
    )

    return value.strftime(
        "%d/%m/%Y %H:%M UTC"
    )


def _base_context(
    request: Request,
    *,
    title: str,
) -> dict:
    return {
        "request": request,
        "title": title,
        "admin_username": (
            request.session.get(
                "admin_username"
            )
            or "Administrateur"
        ),
    }


@router.get(
    "/login",
    response_class=HTMLResponse,
    name="admin-login",
)
def login_page(
    request: Request,
):
    settings = _ensure_enabled(
        request
    )

    if is_admin_authenticated(
        request
    ):
        return RedirectResponse(
            url="/admin",
            status_code=(
                status.HTTP_303_SEE_OTHER
            ),
        )

    csrf_token = ensure_csrf_token(
        request
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={
            "title": "Connexion",
            "csrf_token": csrf_token,
            "error": None,
            "username": (
                settings.admin_username
            ),
        },
    )


@router.post(
    "/login",
    response_class=HTMLResponse,
    name="admin-login-submit",
)
def login_submit(
    request: Request,
    username: Annotated[
        str,
        Form(),
    ],
    password: Annotated[
        str,
        Form(),
    ],
    csrf_token: Annotated[
        str,
        Form(),
    ],
):
    settings = _ensure_enabled(
        request
    )

    csrf_ok = verify_csrf_token(
        request,
        csrf_token,
    )

    username_ok = secrets.compare_digest(
        username.strip(),
        settings.admin_username.strip(),
    )

    password_ok = (
        settings.admin_password_hash
        is not None
        and verify_password(
            password,
            settings.admin_password_hash,
        )
    )

    if not (
        csrf_ok
        and username_ok
        and password_ok
    ):
        new_csrf = ensure_csrf_token(
            request
        )

        return templates.TemplateResponse(
            request=request,
            name="admin/login.html",
            context={
                "title": "Connexion",
                "csrf_token": new_csrf,
                "error": (
                    "Identifiants invalides."
                ),
                "username": username,
            },
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
        )

    request.session.clear()

    request.session[
        "admin_authenticated"
    ] = True

    request.session[
        "admin_username"
    ] = settings.admin_username

    request.session[
        "csrf_token"
    ] = secrets.token_urlsafe(32)

    return RedirectResponse(
        url="/admin",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/logout",
    name="admin-logout",
)
def logout(
    request: Request,
):
    _ensure_enabled(
        request
    )

    request.session.clear()

    return RedirectResponse(
        url="/admin/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get(
    "",
    response_class=HTMLResponse,
    name="admin-dashboard",
)
def dashboard(
    request: Request,
    session: SessionDependency,
):
    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    counts = {
        "clients": session.scalar(
            select(
                func.count(Tenant.id)
            )
        ) or 0,
        "sites": session.scalar(
            select(
                func.count(Site.id)
            )
        ) or 0,
        "agents": session.scalar(
            select(
                func.count(Agent.id)
            )
        ) or 0,
        "activations": session.scalar(
            select(
                func.count(
                    AgentActivationCode.id
                )
            )
        ) or 0,
    }

    recent_agents = list(
        session.scalars(
            select(Agent)
            .order_by(
                Agent.last_seen_at.desc(),
                Agent.id.desc(),
            )
            .limit(5)
        )
    )

    recent_activations = list(
        session.scalars(
            select(
                AgentActivationCode
            )
            .order_by(
                AgentActivationCode
                .created_at
                .desc(),
                AgentActivationCode
                .id
                .desc(),
            )
            .limit(5)
        )
    )

    context = _base_context(
        request,
        title="Tableau de bord",
    )

    context.update(
        {
            "counts": counts,
            "recent_agents": [
                {
                    "uid": agent.agent_uid,
                    "version": agent.version,
                    "environment": (
                        agent.environment
                    ),
                    "last_seen": (
                        _fmt_datetime(
                            agent.last_seen_at
                        )
                    ),
                }
                for agent in recent_agents
            ],
            "recent_activations": [
                {
                    "uid": (
                        activation
                        .activation_uid
                    ),
                    "expires_at": (
                        _fmt_datetime(
                            activation.expires_at
                        )
                    ),
                    "status": (
                        _activation_state(
                            activation
                        )
                    ),

                }
                for activation
                in recent_activations
            ],
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context=context,
    )


def _render_list(
    request: Request,
    *,
    title: str,
    description: str,
    columns: list[str],
    rows: list[list[str]],
    empty_message: str,
):
    context = _base_context(
        request,
        title=title,
    )

    context.update(
        {
            "description": description,
            "columns": columns,
            "rows": rows,
            "empty_message": empty_message,
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/list.html",
        context=context,
    )


def _render_clients(
    request: Request,
    session,
    *,
    error: str | None = None,
    form_name: str = "",
):
    tenants = list(
        session.scalars(
            select(Tenant)
            .order_by(
                Tenant.name,
                Tenant.id,
            )
        )
    )

    context = _base_context(
        request,
        title="Clients",
    )

    context.update(
        {
            "csrf_token": ensure_csrf_token(
                request
            ),
            "clients": [
                {
                    "name": tenant.name,
                    "uid": tenant.tenant_uid,
                    "state": (
                        "Actif"
                        if tenant.is_active
                        else "Inactif"
                    ),
                    "created_at": (
                        _fmt_datetime(
                            tenant.created_at
                        )
                    ),
                }
                for tenant in tenants
            ],
            "error": error,
            "form_name": form_name,
            "success": (
                request.query_params.get(
                    "created"
                )
                == "1"
            ),
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/clients.html",
        context=context,
    )


@router.get(
    "/clients",
    response_class=HTMLResponse,
    name="admin-clients",
)
def clients(
    request: Request,
    session: SessionDependency,
):
    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    return _render_clients(
        request,
        session,
    )


@router.post(
    "/clients",
    response_class=HTMLResponse,
    name="admin-client-create",
)
def create_client(
    request: Request,
    session: SessionDependency,
    name: Annotated[
        str,
        Form(),
    ],
    csrf_token: Annotated[
        str,
        Form(),
    ],
):
    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    if not verify_csrf_token(
        request,
        csrf_token,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail="Jeton CSRF invalide.",
        )

    normalized_name = name.strip()

    if not normalized_name:
        return _render_clients(
            request,
            session,
            error=(
                "Le nom du client est obligatoire."
            ),
            form_name=name,
        )

    try:
        TenantRepository(
            session
        ).create(
            name=normalized_name
        )

    except (
        AuthRepositoryError,
        ValueError,
    ) as exc:

        session.rollback()

        return _render_clients(
            request,
            session,
            error=str(exc),
            form_name=name,
        )

    return RedirectResponse(
        url="/admin/clients?created=1",
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )


def _render_sites(
    request: Request,
    session,
    *,
    error: str | None = None,
    selected_tenant_uid: str = "",
    form_code: str = "",
    form_name: str = "",
):
    tenants = list(
        session.scalars(
            select(Tenant)
            .where(
                Tenant.is_active.is_(True)
            )
            .order_by(
                Tenant.name,
                Tenant.id,
            )
        )
    )

    result = session.execute(
        select(
            Site,
            Tenant.name,
        )
        .join(
            Tenant,
            Tenant.id == Site.tenant_id,
        )
        .order_by(
            Tenant.name,
            Site.name,
            Site.id,
        )
    ).all()

    context = _base_context(
        request,
        title="Sites",
    )

    context.update(
        {
            "csrf_token": ensure_csrf_token(
                request
            ),
            "tenants": tenants,
            "sites": [
                {
                    "name": site.name,
                    "code": site.code,
                    "tenant_name": tenant_name,
                    "uid": site.site_uid,
                    "state": (
                        "Actif"
                        if site.is_active
                        else "Inactif"
                    ),
                }
                for site, tenant_name
                in result
            ],
            "error": error,
            "selected_tenant_uid": (
                selected_tenant_uid
            ),
            "form_code": form_code,
            "form_name": form_name,
            "success": (
                request.query_params.get(
                    "created"
                )
                == "1"
            ),
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/sites.html",
        context=context,
    )


@router.get(
    "/sites",
    response_class=HTMLResponse,
    name="admin-sites",
)
def sites(
    request: Request,
    session: SessionDependency,
):
    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    return _render_sites(
        request,
        session,
    )


@router.post(
    "/sites",
    response_class=HTMLResponse,
    name="admin-site-create",
)
def create_site(
    request: Request,
    session: SessionDependency,
    tenant_uid: Annotated[
        str,
        Form(),
    ],
    code: Annotated[
        str,
        Form(),
    ],
    name: Annotated[
        str,
        Form(),
    ],
    csrf_token: Annotated[
        str,
        Form(),
    ],
):
    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    if not verify_csrf_token(
        request,
        csrf_token,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail="Jeton CSRF invalide.",
        )

    try:
        tenant = TenantRepository(
            session
        ).require_by_uid(
            tenant_uid
        )

        SiteRepository(
            session
        ).create(
            tenant=tenant,
            code=code,
            name=name,
        )

    except (
        AuthRepositoryError,
        ValueError,
    ) as exc:

        session.rollback()

        return _render_sites(
            request,
            session,
            error=str(exc),
            selected_tenant_uid=(
                tenant_uid
            ),
            form_code=code,
            form_name=name,
        )

    return RedirectResponse(
        url="/admin/sites?created=1",
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )


def _agent_is_online(
    last_seen_at: datetime | None,
    *,
    now: datetime | None = None,
    timeout_seconds: int = 180,
) -> bool:
    """
    Un Agent est consid?r? en ligne s'il a ?t? vu
    pendant les trois derniers cycles heartbeat de 60 s.
    """

    if last_seen_at is None:
        return False

    if now is None:
        now = datetime.now(
            timezone.utc
        )

    if last_seen_at.tzinfo is None:
        last_seen_at = (
            last_seen_at.replace(
                tzinfo=timezone.utc
            )
        )

    if now.tzinfo is None:
        now = now.replace(
            tzinfo=timezone.utc
        )

    age = now - last_seen_at

    return age <= timedelta(
        seconds=timeout_seconds
    )


def _agent_update_state(
    agent_version: str,
    current_version: str | None,
) -> tuple[str, str]:

    if not current_version:
        return (
            "R\u00e9f\u00e9rence indisponible",
            "unknown",
        )

    if agent_version == current_version:
        return (
            "\u00c0 jour",
            "ok",
        )

    return (
        "Mise \u00e0 jour disponible",
        "warning",
    )


@router.get(
    "/agents",
    response_class=HTMLResponse,
    name="admin-agents",
)
def agents(
    request: Request,
    session: SessionDependency,
):
    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    result = session.execute(
        select(
            Agent,
            Tenant.name,
            Site.name,
            Site.code,
        )
        .outerjoin(
            Tenant,
            Tenant.id == Agent.tenant_id,
        )
        .outerjoin(
            Site,
            Site.id == Agent.site_id,
        )
        .order_by(
            Agent.id.desc()
        )
    ).all()

    current_release = (
        AgentReleaseRepository(
            session
        ).get_current()
    )

    current_version = (
        current_release.version
        if current_release is not None
        else None
    )

    now = datetime.now(
        timezone.utc
    )

    rows = []

    online_count = 0

    for (
        agent,
        tenant_name,
        site_name,
        site_code,
    ) in result:

        online = _agent_is_online(
            agent.last_seen_at,
            now=now,
        )

        if online:
            online_count += 1

        (
            update_label,
            update_class,
        ) = _agent_update_state(
            agent.version,
            current_version,
        )

        if site_name:
            site_display = (
                f"{site_name} ({site_code})"
                if site_code
                else site_name
            )
        else:
            site_display = "?"

        rows.append(
            {
                "agent_uid":
                    agent.agent_uid,
                "hostname":
                    None,
                "tenant_name":
                    tenant_name or "?",
                "site_name":
                    site_display,
                "version":
                    agent.version,
                "environment":
                    agent.environment,
                "online":
                    online,
                "status_label":
                    (
                        "En ligne"
                        if online
                        else "Hors ligne"
                    ),
                "last_seen":
                    _fmt_datetime(
                        agent.last_seen_at
                    ),
                "created_at":
                    _fmt_datetime(
                        agent.created_at
                    ),
                "update_label":
                    update_label,
                "update_class":
                    update_class,
                "detail_url":
                    str(
                        request.url_for(
                            "admin-agent-detail",
                            agent_uid=(
                                agent.agent_uid
                            ),
                        )
                    ),
            }
        )

    context = _base_context(
        request,
        title="Agents",
    )

    context.update(
        {
            "rows":
                rows,
            "agent_count":
                len(rows),
            "online_count":
                online_count,
            "offline_count":
                len(rows) - online_count,
            "current_version":
                current_version,
            "heartbeat_timeout_seconds":
                180,
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/agents.html",
        context=context,
    )


@router.get(
    "/agents/{agent_uid}",
    response_class=HTMLResponse,
    name="admin-agent-detail",
)
def agent_detail(
    agent_uid: str,
    request: Request,
    session: SessionDependency,
):
    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    normalized_uid = (
        agent_uid.strip()
    )

    result = session.execute(
        select(
            Agent,
            Tenant.name,
            Site.name,
            Site.code,
        )
        .outerjoin(
            Tenant,
            Tenant.id == Agent.tenant_id,
        )
        .outerjoin(
            Site,
            Site.id == Agent.site_id,
        )
        .where(
            Agent.agent_uid
            == normalized_uid
        )
    ).first()

    if result is None:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Agent introuvable.",
        )

    (
        agent,
        tenant_name,
        site_name,
        site_code,
    ) = result

    current_release = (
        AgentReleaseRepository(
            session
        ).get_current()
    )

    current_version = (
        current_release.version
        if current_release is not None
        else None
    )

    online = _agent_is_online(
        agent.last_seen_at
    )

    (
        update_label,
        update_class,
    ) = _agent_update_state(
        agent.version,
        current_version,
    )

    if site_name:
        site_display = (
            f"{site_name} ({site_code})"
            if site_code
            else site_name
        )
    else:
        site_display = "?"

    context = _base_context(
        request,
        title="D?tail Agent",
    )

    context.update(
        {
            "agent":
                agent,
            "tenant_name":
                tenant_name or "?",
            "site_name":
                site_display,
            "online":
                online,
            "status_label":
                (
                    "En ligne"
                    if online
                    else "Hors ligne"
                ),
            "last_seen":
                _fmt_datetime(
                    agent.last_seen_at
                ),
            "created_at":
                _fmt_datetime(
                    agent.created_at
                ),
            "current_version":
                current_version,
            "update_label":
                update_label,
            "update_class":
                update_class,
            "heartbeat_timeout_seconds":
                180,
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/agent_detail.html",
        context=context,
    )



def _activation_state(
    activation: AgentActivationCode,
) -> str:
    if activation.used_at is not None:
        return "Utilis?"

    if not activation.is_active:
        return "Inactif"

    expires = activation.expires_at

    now = utc_now()

    if expires.tzinfo is None:
        expires = expires.replace(
            tzinfo=timezone.utc
        )

    if now.tzinfo is None:
        now = now.replace(
            tzinfo=timezone.utc
        )

    if expires <= now:
        return "Expir?"

    return "Disponible"


def _render_activations(
    request: Request,
    session,
    *,
    error: str | None = None,
    generated_code: str | None = None,
    generated_uid: str | None = None,
    generated_expires_at=None,
    selected_tenant_uid: str = "",
    selected_site_uid: str = "",
    selected_minutes: int = 60,
):
    tenants = list(
        session.scalars(
            select(Tenant)
            .where(
                Tenant.is_active.is_(True)
            )
            .order_by(
                Tenant.name,
                Tenant.id,
            )
        )
    )

    site_result = session.execute(
        select(
            Site,
            Tenant.tenant_uid,
            Tenant.name,
        )
        .join(
            Tenant,
            Tenant.id == Site.tenant_id,
        )
        .where(
            Site.is_active.is_(True),
            Tenant.is_active.is_(True),
        )
        .order_by(
            Tenant.name,
            Site.name,
        )
    ).all()

    activation_result = session.execute(
        select(
            AgentActivationCode,
            Tenant.name,
            Site.name,
            Site.code,
            Agent.agent_uid,
        )
        .join(
            Tenant,
            Tenant.id
            == AgentActivationCode.tenant_id,
        )
        .join(
            Site,
            Site.id
            == AgentActivationCode.site_id,
        )
        .outerjoin(
            Agent,
            Agent.id
            == AgentActivationCode.used_by_agent_id,
        )
        .order_by(
            AgentActivationCode.created_at.desc(),
            AgentActivationCode.id.desc(),
        )
    ).all()

    context = _base_context(
        request,
        title="Activations",
    )

    context.update(
        {
            "csrf_token": ensure_csrf_token(
                request
            ),
            "tenants": tenants,
            "sites": [
                {
                    "uid": site.site_uid,
                    "tenant_uid": tenant_uid,
                    "tenant_name": tenant_name,
                    "name": site.name,
                    "code": site.code,
                }
                for (
                    site,
                    tenant_uid,
                    tenant_name,
                )
                in site_result
            ],
            "activations": [
                {
                    "uid": activation.activation_uid,
                    "tenant_name": tenant_name,
                    "site_name": site_name,
                    "site_code": site_code,
                    "state": _activation_state(
                        activation
                    ),
                    "expires_at": _fmt_datetime(
                        activation.expires_at
                    ),
                    "agent_uid": (
                        agent_uid or "?"
                    ),
                }
                for (
                    activation,
                    tenant_name,
                    site_name,
                    site_code,
                    agent_uid,
                )
                in activation_result
            ],
            "error": error,
            "generated_code": generated_code,
            "generated_uid": generated_uid,
            "generated_expires_at": (
                _fmt_datetime(
                    generated_expires_at
                )
                if generated_expires_at
                is not None
                else None
            ),
            "selected_tenant_uid": (
                selected_tenant_uid
            ),
            "selected_site_uid": (
                selected_site_uid
            ),
            "selected_minutes": (
                selected_minutes
            ),
        }
    )

    response = templates.TemplateResponse(
        request=request,
        name="admin/activations.html",
        context=context,
    )

    if generated_code is not None:
        response.headers[
            "Cache-Control"
        ] = (
            "no-store, no-cache, "
            "must-revalidate, max-age=0"
        )

        response.headers[
            "Pragma"
        ] = "no-cache"

    return response


@router.get(
    "/activations",
    response_class=HTMLResponse,
    name="admin-activations",
)
def activations(
    request: Request,
    session: SessionDependency,
):
    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    return _render_activations(
        request,
        session,
    )


@router.post(
    "/activations",
    response_class=HTMLResponse,
    name="admin-activation-create",
)
def create_activation(
    request: Request,
    session: SessionDependency,
    tenant_uid: Annotated[
        str,
        Form(),
    ],
    site_uid: Annotated[
        str,
        Form(),
    ],
    expires_in_minutes: Annotated[
        int,
        Form(),
    ],
    csrf_token: Annotated[
        str,
        Form(),
    ],
):
    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    if not verify_csrf_token(
        request,
        csrf_token,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail="Jeton CSRF invalide.",
        )

    try:
        tenant = TenantRepository(
            session
        ).require_by_uid(
            tenant_uid
        )

        site = SiteRepository(
            session
        ).require_by_uid(
            site_uid
        )

        if site.tenant_id != tenant.id:
            raise ValueError(
                "Le site ne correspond pas "
                "au client s?lectionn?."
            )

        activation, raw_code = (
            AgentActivationCodeRepository(
                session
            ).create(
                tenant=tenant,
                site=site,
                expires_in_minutes=(
                    expires_in_minutes
                ),
            )
        )

    except (
        ActivationCodeError,
        AuthRepositoryError,
        ValueError,
    ) as exc:

        session.rollback()

        return _render_activations(
            request,
            session,
            error=str(exc),
            selected_tenant_uid=tenant_uid,
            selected_site_uid=site_uid,
            selected_minutes=(
                expires_in_minutes
            ),
        )

    return _render_activations(
        request,
        session,
        generated_code=raw_code,
        generated_uid=(
            activation.activation_uid
        ),
        generated_expires_at=(
            activation.expires_at
        ),
        selected_tenant_uid=tenant_uid,
        selected_site_uid=site_uid,
        selected_minutes=(
            expires_in_minutes
        ),
    )


@router.post(
    "/activations/{activation_uid}/revoke",
    name="admin-activation-revoke",
)
def revoke_activation(
    request: Request,
    session: SessionDependency,
    activation_uid: str,
    csrf_token: Annotated[
        str,
        Form(),
    ],
):
    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    if not verify_csrf_token(
        request,
        csrf_token,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail="Jeton CSRF invalide.",
        )

    try:
        AgentActivationCodeRepository(
            session
        ).revoke(
            activation_uid
        )

    except (
        ActivationCodeError,
        AuthRepositoryError,
        ValueError,
    ) as exc:

        session.rollback()

        return _render_activations(
            request,
            session,
            error=str(exc),
        )

    return RedirectResponse(
        url="/admin/activations",
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )


# ============================================================
# Distribution Agent Windows
# ============================================================

_AGENT_RELEASE_EXTENSIONS = {
    ".exe",
    ".msi",
    ".zip",
}


def _fmt_file_size(
    value: int,
) -> str:

    size = float(value)

    for unit in (
        "B",
        "KB",
        "MB",
        "GB",
    ):

        if size < 1024 or unit == "GB":
            return (
                f"{size:.1f} {unit}"
                if unit != "B"
                else f"{int(size)} B"
            )

        size /= 1024

    return f"{value} B"


def _release_storage_root(
    settings: Settings,
) -> Path:

    return Path(
        settings.agent_release_storage_dir
    ).expanduser().resolve()


def _release_file_path(
    settings: Settings,
    storage_path: str,
) -> Path:

    root = _release_storage_root(
        settings
    )

    candidate = (
        root
        / storage_path
    ).resolve()

    try:
        candidate.relative_to(
            root
        )

    except ValueError as exc:
        raise ValueError(
            "Chemin de fichier Agent invalide."
        ) from exc

    return candidate


def _release_view(
    release,
) -> dict:

    if release.archived_at is not None:
        state = "archive"

    elif release.is_published:
        state = "published"

    elif release.published_at is not None:
        state = "previous"

    else:
        state = "draft"

    return {
        "uid": release.release_uid,
        "version": release.version,
        "filename": release.filename,
        "sha256": release.sha256,
        "size": _fmt_file_size(
            release.file_size
        ),
        "notes": (
            release.release_notes
            or ""
        ),
        "state": state,
        "published": (
            release.is_published
        ),
        "archived": (
            release.archived_at
            is not None
        ),
        "created_at": _fmt_datetime(
            release.created_at
        ),
        "published_at": (
            _fmt_datetime(
                release.published_at
            )
            if release.published_at
            is not None
            else "-"
        ),
    }


def _render_agent_windows(
    request: Request,
    session,
    *,
    error: str | None = None,
    form_version: str = "",
    form_notes: str = "",
):

    settings = _settings(
        request
    )

    repository = (
        AgentReleaseRepository(
            session
        )
    )

    releases = repository.list_all()

    current = repository.get_current()

    context = _base_context(
        request,
        title="Agent Windows",
    )

    context.update(
        {
            "csrf_token": ensure_csrf_token(
                request
            ),
            "releases": [
                _release_view(release)
                for release in releases
            ],
            "current": (
                _release_view(current)
                if current is not None
                else None
            ),
            "error": error,
            "form_version": form_version,
            "form_notes": form_notes,
            "max_upload_mb": (
                settings
                .agent_release_max_upload_bytes
                // 1024
                // 1024
            ),
            "uploaded": (
                request.query_params.get(
                    "uploaded"
                )
                == "1"
            ),
            "published": (
                request.query_params.get(
                    "published"
                )
                == "1"
            ),
            "archived": (
                request.query_params.get(
                    "archived"
                )
                == "1"
            ),
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/agent_windows.html",
        context=context,
    )


@router.get(
    "/agent-windows",
    response_class=HTMLResponse,
    name="admin-agent-windows",
)
def agent_windows(
    request: Request,
    session: SessionDependency,
):

    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    return _render_agent_windows(
        request,
        session,
    )


@router.post(
    "/agent-windows",
    response_class=HTMLResponse,
    name="admin-agent-release-upload",
)
def upload_agent_release(
    request: Request,
    session: SessionDependency,
    version: Annotated[
        str,
        Form(),
    ],
    release_notes: Annotated[
        str,
        Form(),
    ],
    csrf_token: Annotated[
        str,
        Form(),
    ],
    installer: Annotated[
        UploadFile,
        File(),
    ],
):

    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    if not verify_csrf_token(
        request,
        csrf_token,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail="Jeton CSRF invalide.",
        )

    settings = _settings(
        request
    )

    normalized_version = (
        version.strip()
    )

    normalized_notes = (
        release_notes.strip()
    )

    allowed_version_chars = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "._-"
    )

    if (
        not normalized_version
        or len(normalized_version) > 64
        or not normalized_version[0].isalnum()
        or any(
            character
            not in allowed_version_chars
            for character
            in normalized_version
        )
    ):
        return _render_agent_windows(
            request,
            session,
            error=(
                "Version invalide. "
                "Utilisez uniquement lettres, "
                "chiffres, point, tiret "
                "et underscore."
            ),
            form_version=version,
            form_notes=release_notes,
        )

    if len(normalized_notes) > 5000:
        return _render_agent_windows(
            request,
            session,
            error=(
                "Les notes de version "
                "sont trop longues."
            ),
            form_version=version,
            form_notes=release_notes,
        )

    repository = (
        AgentReleaseRepository(
            session
        )
    )

    if repository.get_by_version(
        normalized_version
    ) is not None:

        return _render_agent_windows(
            request,
            session,
            error=(
                "Cette version existe "
                "deja."
            ),
            form_version=version,
            form_notes=release_notes,
        )

    raw_filename = (
        installer.filename
        or ""
    )

    filename = (
        raw_filename
        .replace("\\", "/")
        .split("/")[-1]
        .strip()
    )

    if (
        not filename
        or filename in {
            ".",
            "..",
        }
    ):
        return _render_agent_windows(
            request,
            session,
            error=(
                "Nom de fichier invalide."
            ),
            form_version=version,
            form_notes=release_notes,
        )

    extension = (
        Path(filename)
        .suffix
        .lower()
    )

    if (
        extension
        not in _AGENT_RELEASE_EXTENSIONS
    ):
        return _render_agent_windows(
            request,
            session,
            error=(
                "Format de fichier non autorise. "
                "Formats acceptes : "
                ".exe, .msi, .zip."
            ),
            form_version=version,
            form_notes=release_notes,
        )

    storage_root = (
        _release_storage_root(
            settings
        )
    )

    storage_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_directory = (
        storage_root
        / ".uploads"
    )

    temp_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = (
        temp_directory
        / (
            secrets.token_hex(16)
            + ".upload"
        )
    )

    digest = hashlib.sha256()

    total_size = 0

    try:

        with temp_path.open(
            "xb"
        ) as destination:

            while True:

                chunk = (
                    installer.file.read(
                        1024 * 1024
                    )
                )

                if not chunk:
                    break

                total_size += len(
                    chunk
                )

                if (
                    total_size
                    >
                    settings
                    .agent_release_max_upload_bytes
                ):
                    raise ValueError(
                        "Le fichier depasse "
                        "la taille maximale "
                        "autorisee."
                    )

                digest.update(
                    chunk
                )

                destination.write(
                    chunk
                )

        if total_size <= 0:
            raise ValueError(
                "Le fichier est vide."
            )

        with temp_path.open(
            "rb"
        ) as source:

            signature = source.read(
                8
            )

        if (
            extension == ".exe"
            and not signature.startswith(
                b"MZ"
            )
        ):
            raise ValueError(
                "Le fichier .exe "
                "n'a pas une signature "
                "Windows valide."
            )

        if (
            extension == ".zip"
            and not signature.startswith(
                b"PK"
            )
        ):
            raise ValueError(
                "Le fichier .zip "
                "n'a pas une signature ZIP "
                "valide."
            )

        if (
            extension == ".msi"
            and signature
            != bytes.fromhex(
                "D0CF11E0A1B11AE1"
            )
        ):
            raise ValueError(
                "Le fichier .msi "
                "n'a pas une signature MSI "
                "valide."
            )

        release_directory = (
            storage_root
            / normalized_version
        )

        release_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        final_path = (
            release_directory
            / filename
        ).resolve()

        try:
            final_path.relative_to(
                storage_root
            )

        except ValueError as exc:
            raise ValueError(
                "Chemin final invalide."
            ) from exc

        if final_path.exists():
            raise ValueError(
                "Un fichier avec ce nom "
                "existe deja pour "
                "cette version."
            )

        temp_path.replace(
            final_path
        )

        relative_storage_path = (
            normalized_version
            + "/"
            + filename
        )

        try:

            repository.create(
                version=normalized_version,
                filename=filename,
                storage_path=(
                    relative_storage_path
                ),
                sha256=digest.hexdigest(),
                file_size=total_size,
                release_notes=(
                    normalized_notes
                    or None
                ),
            )

            # Le commit explicite permet de ne pas
            # conserver un fichier orphelin si la DB
            # refuse finalement la release.
            session.commit()

        except Exception:

            session.rollback()

            final_path.unlink(
                missing_ok=True
            )

            raise

    except (
        AgentReleaseRepositoryError,
        ValueError,
        OSError,
    ) as exc:

        temp_path.unlink(
            missing_ok=True
        )

        return _render_agent_windows(
            request,
            session,
            error=str(exc),
            form_version=version,
            form_notes=release_notes,
        )

    finally:

        try:
            installer.file.close()
        except Exception:
            pass

    return RedirectResponse(
        url=(
            "/admin/agent-windows"
            "?uploaded=1"
        ),
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )


@router.post(
    "/agent-windows/{release_uid}/publish",
    name="admin-agent-release-publish",
)
def publish_agent_release(
    request: Request,
    session: SessionDependency,
    release_uid: str,
    csrf_token: Annotated[
        str,
        Form(),
    ],
):

    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    if not verify_csrf_token(
        request,
        csrf_token,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail="Jeton CSRF invalide.",
        )

    try:

        AgentReleaseRepository(
            session
        ).publish(
            release_uid
        )

    except (
        AgentReleaseRepositoryError,
        ValueError,
    ) as exc:

        session.rollback()

        return _render_agent_windows(
            request,
            session,
            error=str(exc),
        )

    return RedirectResponse(
        url=(
            "/admin/agent-windows"
            "?published=1"
        ),
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )


@router.post(
    "/agent-windows/{release_uid}/archive",
    name="admin-agent-release-archive",
)
def archive_agent_release(
    request: Request,
    session: SessionDependency,
    release_uid: str,
    csrf_token: Annotated[
        str,
        Form(),
    ],
):

    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    if not verify_csrf_token(
        request,
        csrf_token,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail="Jeton CSRF invalide.",
        )

    try:

        AgentReleaseRepository(
            session
        ).archive(
            release_uid
        )

    except (
        AgentReleaseRepositoryError,
        ValueError,
    ) as exc:

        session.rollback()

        return _render_agent_windows(
            request,
            session,
            error=str(exc),
        )

    return RedirectResponse(
        url=(
            "/admin/agent-windows"
            "?archived=1"
        ),
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )


@router.get(
    "/agent-windows/{release_uid}/download",
    name="admin-agent-release-download",
)
def download_agent_release_admin(
    request: Request,
    session: SessionDependency,
    release_uid: str,
):

    redirect = _require_admin(
        request
    )

    if redirect is not None:
        return redirect

    release = (
        AgentReleaseRepository(
            session
        ).get_by_uid(
            release_uid
        )
    )

    if release is None:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Version Agent introuvable."
            ),
        )

    try:

        file_path = (
            _release_file_path(
                _settings(request),
                release.storage_path,
            )
        )

    except ValueError:

        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Fichier Agent introuvable."
            ),
        )

    if (
        not file_path.is_file()
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Fichier Agent introuvable."
            ),
        )

    return FileResponse(
        path=file_path,
        filename=release.filename,
        media_type=(
            "application/octet-stream"
        ),
        headers={
            "X-Content-Type-Options":
                "nosniff",
        },
    )
