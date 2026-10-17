"""DAT-21 : taille d'échantillon."""

from decimal import Decimal

import pytest

from app.analytics.sampling import (
    SamplingError,
    attribute_sample_size,
    binomial_cdf,
    expansion_factor,
    mus_sample_size,
    poisson_factor,
)
from app.security.roles import Role


def test_facteurs_de_confiance_de_poisson():
    # Valeurs publiées (AICPA, tables de facteurs de confiance MUS).
    assert poisson_factor(0, 0.95) == pytest.approx(3.00, abs=0.01)
    assert poisson_factor(0, 0.90) == pytest.approx(2.31, abs=0.01)
    assert poisson_factor(1, 0.95) == pytest.approx(4.75, abs=0.01)
    assert poisson_factor(2, 0.95) == pytest.approx(6.30, abs=0.01)
    assert expansion_factor(Decimal("0.95")) == Decimal("1.6")
    assert expansion_factor(Decimal("0.92")) == Decimal("1.6")
    assert expansion_factor(Decimal("0.5")) == Decimal("1.15")
    assert expansion_factor(Decimal("0.995")) == Decimal("1.9")


@pytest.mark.parametrize(
    ("confidence", "tolerable", "expected", "size"),
    [(0.95, 0.05, 0, 59), (0.90, 0.05, 0, 45), (0.95, 0.10, 0, 29), (0.90, 0.10, 0, 22)],
)
def test_dat21_attributs_sans_ecart_attendu(confidence, tolerable, expected, size):
    assert attribute_sample_size(confidence, tolerable, expected) == size


def test_dat21_attributs_avec_ecarts_attendus():
    n = attribute_sample_size(0.95, 0.05, 0.01)
    k = -(-n // 100)  # ⌈n × 1 %⌉
    assert binomial_cdf(k, n, 0.05) <= 0.05 < binomial_cdf(-(-(n - 1) // 100), n - 1, 0.05)
    assert n > 59 and attribute_sample_size(0.95, 0.05, 0.02) > n
    with pytest.raises(SamplingError):
        attribute_sample_size(0.95, 0.05, 0.05)
    with pytest.raises(SamplingError, match="5 000"):
        attribute_sample_size(0.99, 0.011, 0.0109)


def test_dat21_mus():
    # 5 000 000 × 3,0 / (250 000 − 50 000 × 1,6) = 88,2 → 89
    assert (
        mus_sample_size(Decimal(5_000_000), Decimal("0.95"), Decimal(250_000), Decimal(50_000))
        == 89
    )
    assert mus_sample_size(Decimal(1_000_000), Decimal("0.90"), Decimal(50_000), Decimal(0)) == 47
    with pytest.raises(SamplingError):
        mus_sample_size(Decimal(1000), Decimal("0.95"), Decimal(100), Decimal(100))


def test_dat21_api(client, account):
    h = account(Role.AUDITEUR).headers
    r = client.post("/api/sampling/size", json={"type": "mus", "confiance": "0.95",
                    "population": "5000000", "erreur_tolerable": "250000",
                    "erreur_attendue": "50000"}, headers=h)  # fmt: skip
    assert r.status_code == 200
    assert r.json()["taille"] == 89 and r.json()["intervalle"] == "56179.78"
    r = client.post("/api/sampling/size", json={"type": "attributs", "confiance": "0.95",
                    "taux_tolerable": "0.05"}, headers=h)  # fmt: skip
    assert r.json()["taille"] == 59
    r = client.post("/api/sampling/size", json={"type": "mus", "confiance": "0.95"}, headers=h)
    assert r.status_code == 422
    r = client.post("/api/sampling/size", json={"type": "attributs", "confiance": "0.95"},
                    headers=h)  # fmt: skip
    assert r.status_code == 422
    audite = account(Role.AUDITE).headers
    r = client.post("/api/sampling/size", json={"type": "attributs", "confiance": "0.95",
                    "taux_tolerable": "0.05"}, headers=audite)  # fmt: skip
    assert r.status_code == 403
