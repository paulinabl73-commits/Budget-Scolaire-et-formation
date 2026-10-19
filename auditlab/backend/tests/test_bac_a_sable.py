"""DAT-27 : exécution des scripts isolée (sans réseau, mémoire et durée bornées)."""

from pathlib import Path

import pytest

from app.config import get_settings
from app.scripting import runner
from tests.test_datasets import ctx  # noqa: F401


def _run(client, ctx, code):  # noqa: F811
    da = ctx["da"].headers
    s = client.post(f"{ctx['url']}/scripts", json={"nom": "Isolement", "code": code}, headers=da)
    run = client.post(f"/api/scripts/{s.json()['id']}/runs", headers=da).json()
    return client.get(f"/api/script-runs/{run['id']}", headers=da).json()


NETWORK = """
import socket
s = socket.socket()
s.settimeout(3)
s.connect(("1.1.1.1", 80))
"""


def test_dat27_sans_reseau(client, ctx):  # noqa: F811
    run = _run(client, ctx, NETWORK)
    assert (
        run["statut"] == "erreur" and "OSError" in run["erreur"] or "unreachable" in run["erreur"]
    )


def test_dat27_memoire_bornee(client, ctx, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "scripts_memory_mb", 1024)
    run = _run(client, ctx, "x = bytearray(1500 * 1024 * 1024)\n")
    assert run["statut"] == "erreur" and "Mémoire maximale dépassée" in run["erreur"]


def test_dat27_duree_bornee(client, ctx, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "scripts_timeout_s", 2)
    run = _run(
        client,
        ctx,
        "import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', 'while True: pass'])\nwhile True:\n    pass\n",
    )
    assert run["statut"] == "erreur" and run["erreur"] == "Durée maximale dépassée (2 s)"
    assert run["duree_ms"] < 15000


def test_dat27_jamais_sans_isolement(client, ctx, monkeypatch):  # noqa: F811
    monkeypatch.setattr(runner.shutil, "which", lambda _: None)
    run = _run(client, ctx, "print('ok')\n")
    assert run["statut"] == "erreur" and "Bac à sable indisponible" in run["erreur"]
    monkeypatch.setattr(get_settings(), "scripts_sandbox", "aucun")
    assert "Bac à sable inconnu" in _run(client, ctx, "print('ok')\n")["erreur"]


def test_dat27_commande_docker(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "scripts_work_dir", "/data/scripts")
    monkeypatch.setattr(s, "scripts_work_host_dir", "/srv/auditlab/scripts")
    monkeypatch.setattr(s, "scripts_docker_runtime", "runsc")
    cmd = runner.docker_command(Path("/data/scripts/abc"), "auditlab-script-abc")
    joined = " ".join(cmd)
    for part in (
        "--network none",
        "--memory 2048m",
        "--memory-swap 2048m",
        "--read-only",
        "--cap-drop ALL",
        "--user 65534:65534",
        "--runtime runsc",
        "/srv/auditlab/scripts/abc:/work:ro",
        "/srv/auditlab/scripts/abc/out:/work/out:rw",
    ):
        assert part in joined, part
    assert cmd[-4:] == ["python", "-I", s.scripts_bootstrap_path, "/work"]


@pytest.mark.parametrize("code", [137, -9])
def test_dat27_arret_par_le_noyau(client, ctx, monkeypatch, code):  # noqa: F811
    monkeypatch.setattr(runner, "execute", lambda work: runner.Completed(code, ""))
    run = _run(client, ctx, "print('ok')\n")
    assert run["erreur"].startswith("Exécution arrêtée : mémoire (2048 Mo)")
