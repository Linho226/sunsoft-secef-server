from __future__ import annotations

import argparse
from datetime import timezone

from sunsoft_secef_server.config import (
    get_settings,
)
from sunsoft_secef_server.storage.auth_repositories import (
    AgentActivationCodeRepository,
    SiteRepository,
    TenantRepository,
)
from sunsoft_secef_server.storage.database import (
    Database,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Provisionne un Client Sunsoft SECeF, "
            "son Site et un code d'activation Agent."
        )
    )

    parser.add_argument(
        "--tenant-name",
        required=True,
        help="Nom commercial du Client.",
    )

    parser.add_argument(
        "--site-code",
        required=True,
        help=(
            "Code court du Site, "
            "par exemple SIEGE ou BOUTIQUE01."
        ),
    )

    parser.add_argument(
        "--site-name",
        required=True,
        help="Nom lisible du Site.",
    )

    parser.add_argument(
        "--expires-minutes",
        type=int,
        default=60,
        help=(
            "Dur?e de validit? du code "
            "entre 1 et 1440 minutes."
        ),
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    settings = get_settings()

    database = Database(
        settings.database_url
    )

    session = database.session()

    try:
        with session.begin():

            tenant = TenantRepository(
                session
            ).create(
                name=args.tenant_name,
            )

            site = SiteRepository(
                session
            ).create(
                tenant=tenant,
                code=args.site_code,
                name=args.site_name,
            )

            activation, raw_code = (
                AgentActivationCodeRepository(
                    session
                ).create(
                    tenant=tenant,
                    site=site,
                    expires_in_minutes=(
                        args.expires_minutes
                    ),
                )
            )

            tenant_uid = tenant.tenant_uid
            site_uid = site.site_uid
            site_code = site.code
            activation_uid = (
                activation.activation_uid
            )
            expires_at = (
                activation.expires_at
            )

        print()
        print(
            "SUNSOFT SECEF - PROVISIONING OK"
        )
        print(
            "TENANT_UID =",
            tenant_uid,
        )
        print(
            "SITE_UID =",
            site_uid,
        )
        print(
            "SITE_CODE =",
            site_code,
        )
        print(
            "ACTIVATION_UID =",
            activation_uid,
        )

        if (
            expires_at.tzinfo
            is not None
        ):
            expires_at = (
                expires_at
                .astimezone(
                    timezone.utc
                )
            )

        print(
            "EXPIRES_AT =",
            expires_at.isoformat(),
        )

        print()
        print(
            "ACTIVATION_CODE =",
            raw_code,
        )
        print()
        print(
            "IMPORTANT: ce code brut "
            "n'est pas stock? en base."
        )

        return 0

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
