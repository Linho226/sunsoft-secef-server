from fastapi import (
    APIRouter,
    HTTPException,
    status,
)
from sqlalchemy import select

from sunsoft_secef_server.activation_schemas import (
    AgentActivationRequest,
    AgentActivationResponse,
)
from sunsoft_secef_server.api.dependencies import (
    SessionDependency,
)
from sunsoft_secef_server.storage.auth_repositories import (
    AgentActivationCodeRepository,
    AgentCredentialRepository,
    ActivationCodeUnavailableError,
    AuthRepositoryError,
)
from sunsoft_secef_server.storage.models import (
    Agent,
    Site,
    Tenant,
    utc_now,
)


router = APIRouter(
    tags=["agents"],
)


def _activation_unavailable() -> None:
    """
    R?ponse volontairement g?n?rique.

    Ne r?v?le pas si le code est inconnu,
    expir?, utilis? ou li? ? un autre Agent.
    """

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Activation indisponible.",
    )


def _load_context(
    session,
    activation,
) -> tuple[Tenant, Site]:
    tenant = session.get(
        Tenant,
        activation.tenant_id,
    )

    site = session.get(
        Site,
        activation.site_id,
    )

    if (
        tenant is None
        or site is None
        or not tenant.is_active
        or not site.is_active
        or site.tenant_id != tenant.id
    ):
        _activation_unavailable()

    return tenant, site


@router.post(
    "/activate",
    response_model=AgentActivationResponse,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": (
                "Code indisponible ou "
                "provisioning incompatible."
            ),
        },
    },
)
def activate_agent(
    payload: AgentActivationRequest,
    session: SessionDependency,
) -> AgentActivationResponse:
    """
    Provisionne un Agent Windows.

    Le credential permanent est g?n?r? localement
    sur Windows. Le serveur ne persiste que son hash.

    Le m?me appel peut ?tre rejou? apr?s une perte
    r?seau sans g?n?rer un nouveau credential.
    """

    raw_code = (
        payload.activation_code
        .get_secret_value()
    )

    raw_token = (
        payload.server_api_token
        .get_secret_value()
    )

    recovered = False

    try:
        with session.begin():

            activation_repository = (
                AgentActivationCodeRepository(
                    session
                )
            )

            credential_repository = (
                AgentCredentialRepository(
                    session
                )
            )

            # ----------------------------------------
            # Reprise d'une activation d?j? termin?e.
            # ----------------------------------------

            recovery = (
                activation_repository
                .recover_for_agent(
                    code=raw_code,
                    agent_uid=payload.agent_uid,
                )
            )

            if recovery is not None:
                activation, agent = recovery

                tenant, site = _load_context(
                    session,
                    activation,
                )

                credential = (
                    credential_repository
                    .provision_with_token(
                        agent=agent,
                        token=raw_token,
                        replace_existing=False,
                    )
                )

                agent.version = payload.version
                agent.environment = (
                    payload.environment
                )
                agent.last_seen_at = utc_now()

                recovered = True

            else:
                # ------------------------------------
                # Premi?re utilisation du code.
                # ------------------------------------

                try:
                    activation = (
                        activation_repository
                        .claim(
                            raw_code
                        )
                    )
                except (
                    ActivationCodeUnavailableError
                ):
                    # Un appel concurrent peut avoir
                    # termin? l'activation pendant que
                    # celui-ci attendait PostgreSQL.
                    recovery = (
                        activation_repository
                        .recover_for_agent(
                            code=raw_code,
                            agent_uid=payload.agent_uid,
                        )
                    )

                    if recovery is None:
                        _activation_unavailable()

                    activation, agent = recovery

                    tenant, site = _load_context(
                        session,
                        activation,
                    )

                    credential = (
                        credential_repository
                        .provision_with_token(
                            agent=agent,
                            token=raw_token,
                            replace_existing=False,
                        )
                    )

                    agent.version = payload.version
                    agent.environment = (
                        payload.environment
                    )
                    agent.last_seen_at = utc_now()

                    recovered = True

                else:
                    tenant, site = _load_context(
                        session,
                        activation,
                    )

                    existing_agent = session.scalar(
                        select(
                            Agent
                        ).where(
                            Agent.agent_uid
                            == payload.agent_uid
                        )
                    )

                    if existing_agent is None:
                        agent = Agent(
                            tenant_id=tenant.id,
                            site_id=site.id,
                            agent_uid=payload.agent_uid,
                            version=payload.version,
                            environment=(
                                payload.environment
                            ),
                        )

                        session.add(
                            agent
                        )

                        session.flush()

                    else:
                        agent = existing_agent

                        if (
                            agent.tenant_id
                            != tenant.id
                            or agent.site_id
                            != site.id
                        ):
                            _activation_unavailable()

                        agent.version = payload.version
                        agent.environment = (
                            payload.environment
                        )
                        agent.last_seen_at = utc_now()

                    activation_repository.bind_agent(
                        activation=activation,
                        agent=agent,
                    )

                    # Nouveau code d'activation :
                    # autorise le remplacement d'un
                    # ancien credential du m?me Agent.
                    credential = (
                        credential_repository
                        .provision_with_token(
                            agent=agent,
                            token=raw_token,
                            replace_existing=True,
                        )
                    )

            response = AgentActivationResponse(
                status="activated",
                agent_uid=agent.agent_uid,
                tenant_uid=tenant.tenant_uid,
                site_uid=site.site_uid,
                site_code=site.code,
                credential_uid=(
                    credential.credential_uid
                ),
                recovered=recovered,
            )

        return response

    except HTTPException:
        raise

    except AuthRepositoryError:
        _activation_unavailable()
