from datetime import (
    datetime,
    timedelta,
    timezone,
)
from types import SimpleNamespace
from unittest.mock import patch

from sunsoft_secef_server.admin import (
    routes,
)


NOW = datetime(
    2026,
    11,
    16,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def make_status(
    *,
    age: int,
    stale: bool = False,
    updated_ago: int = 0,
):
    return SimpleNamespace(
        connection_age_seconds=age,
        connection_stale=stale,
        status_updated_at=(
            NOW
            - timedelta(
                seconds=updated_ago
            )
        ),
    )


def test_mcf_admin_state_is_unavailable_without_status(
) -> None:
    label, css_class, age = (
        routes._mcf_admin_state(
            None
        )
    )

    assert label == "Indisponible"
    assert css_class == "unknown"
    assert age is None


def test_mcf_admin_state_is_ok_at_exactly_seven_days(
) -> None:
    status = make_status(
        age=7 * 24 * 60 * 60,
    )

    with patch.object(
        routes,
        "utc_now",
        return_value=NOW,
    ):
        label, css_class, age = (
            routes._mcf_admin_state(
                status
            )
        )

    assert label == "OK"
    assert css_class == "ok"

    assert (
        age
        == 7 * 24 * 60 * 60
    )


def test_mcf_admin_state_is_warning_over_seven_days(
) -> None:
    status = make_status(
        age=(
            7 * 24 * 60 * 60
            + 1
        ),
    )

    with patch.object(
        routes,
        "utc_now",
        return_value=NOW,
    ):
        label, css_class, age = (
            routes._mcf_admin_state(
                status
            )
        )

    assert (
        label
        == "Alerte > 7 jours"
    )

    assert css_class == "warning"

    assert (
        age
        == 7 * 24 * 60 * 60 + 1
    )


def test_mcf_status_continues_to_age_on_central_server(
) -> None:
    """
    Cas critique :
    le dernier C2 etait encore recent,
    puis aucun nouveau C2 n'a ete recu.

    Le serveur doit faire vieillir
    l'information sans modifier la DB.
    """

    threshold = (
        7 * 24 * 60 * 60
    )

    status = make_status(
        age=threshold - 5,
        updated_ago=10,
    )

    with patch.object(
        routes,
        "utc_now",
        return_value=NOW,
    ):
        label, css_class, age = (
            routes._mcf_admin_state(
                status
            )
        )

    assert (
        age
        == threshold + 5
    )

    assert (
        label
        == "Alerte > 7 jours"
    )

    assert css_class == "warning"


def test_explicit_stale_flag_remains_warning(
) -> None:
    status = make_status(
        age=30,
        stale=True,
    )

    with patch.object(
        routes,
        "utc_now",
        return_value=NOW,
    ):
        label, css_class, age = (
            routes._mcf_admin_state(
                status
            )
        )

    assert (
        label
        == "Alerte > 7 jours"
    )

    assert css_class == "warning"
    assert age == 30


def test_formats_raw_mcf_datetime_without_timezone_conversion(
) -> None:
    assert (
        routes._fmt_mcf_device_datetime(
            "20261116093000"
        )
        == "16/11/2026 09:30:00"
    )

    assert (
        routes._fmt_mcf_device_datetime(
            None
        )
        == "?"
    )

    assert (
        routes._fmt_mcf_device_datetime(
            "invalid"
        )
        == "?"
    )


def test_formats_mcf_age(
) -> None:
    assert (
        routes._fmt_mcf_age(
            30
        )
        == "30 s"
    )

    assert (
        routes._fmt_mcf_age(
            8100
        )
        == "2 h 15 min"
    )

    assert (
        routes._fmt_mcf_age(
            7 * 86400 + 60
        )
        == "7 j 0 h 1 min"
    )
