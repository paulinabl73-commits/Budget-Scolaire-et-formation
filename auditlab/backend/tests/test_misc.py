import json
import logging

import pytest

from app.cli import main as cli_main
from app.logging_config import JsonFormatter
from app.security import totp
from app.security.passwords import check_password_policy, verify_password
from app.security.roles import ROLE_PERMISSIONS, Perm, Role, can_review, has_permission


def test_matrice_des_droits():
    assert has_permission("administrateur", Perm.USERS_MANAGE)
    assert not has_permission("directeur_audit", Perm.USERS_MANAGE)
    assert has_permission("directeur_audit", Perm.PLAN_VALIDATE)
    assert has_permission("data_analyst", Perm.DATA_PUBLISH_LIBRARY)
    assert not has_permission("auditeur", Perm.DATA_PUBLISH_LIBRARY)
    assert has_permission("auditeur", Perm.WORKPAPERS_PREPARE)
    assert not has_permission("auditeur", Perm.WORKPAPERS_REVIEW)
    assert ROLE_PERMISSIONS[Role.AUDITE] == {Perm.FINDINGS_RESPOND}
    assert not has_permission("inconnu", Perm.DATA_READ)


def test_separation_des_taches():
    assert can_review("a", "b")
    assert not can_review("a", "a")


def test_route_des_roles(client, account):
    roles = client.get("/api/roles", headers=account(Role.AUDITEUR).headers).json()
    assert len(roles) == 8  # dont les deux rôles du Module 5
    admin = next(r for r in roles if r["code"] == "administrateur")
    assert admin["mfa_obligatoire"] is True and admin["libelle"] == "Administrateur"
    associe = next(r for r in roles if r["code"] == "associe_signataire")
    assert associe["mfa_obligatoire"] is True and associe["libelle"] == "Associé signataire"


def test_sante(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_en_tete_request_id(client):
    resp = client.get("/api/health", headers={"X-Request-ID": "abc"})
    assert resp.headers["X-Request-ID"] == "abc"


def test_politique_de_mot_de_passe():
    assert check_password_policy("MotDePasse-Solide-2026") == []
    assert len(check_password_policy("abc")) == 3


def test_hash_invalide():
    assert verify_password("pas-un-hash", "x") is False


def test_code_totp_non_numerique():
    assert totp.verify_code(totp.new_secret(), "abcdef") is False


def test_journalisation_json():
    record = logging.LogRecord("t", logging.INFO, "f", 1, "message é", None, None)
    record.status = 200
    out = json.loads(JsonFormatter().format(record))
    assert out["message"] == "message é" and out["status"] == 200 and out["level"] == "INFO"
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    assert "boom" in json.loads(JsonFormatter().format(record))["exc"]


def test_creation_administrateur_en_ligne_de_commande(monkeypatch, capsys):
    monkeypatch.setenv("AUDITLAB_ADMIN_PASSWORD", "faible")
    assert cli_main(["create-admin", "--email", "a@exemple.org"]) == 2
    monkeypatch.setenv("AUDITLAB_ADMIN_PASSWORD", "MotDePasse-Solide-2026")
    assert cli_main(["create-admin", "--email", "A@exemple.org"]) == 0
    assert "créé" in capsys.readouterr().out
    assert cli_main(["create-admin", "--email", "a@exemple.org"]) == 0
    assert "existe déjà" in capsys.readouterr().out


def test_commande_inconnue():
    with pytest.raises(SystemExit):
        cli_main(["inconnue"])
