"""DAT-29 : planification d'un script (quotidienne, mensuelle) et alerte au-delà d'un seuil."""

import datetime as dt

import polars as pl
from sqlalchemy import select

from app.models import Script
from app.models.notification import Notification
from app.scripting.schedule import next_run, run_due
from app.tasks import scheduled_scripts
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401

UTC = dt.UTC


def test_dat29_echeances():
    at = dt.datetime(2026, 1, 31, 7, 30, tzinfo=UTC)
    assert next_run({"frequence": "quotidienne", "heure": 6}, at) == dt.datetime(
        2026, 2, 1, 6, tzinfo=UTC
    )
    assert next_run({"frequence": "quotidienne", "heure": 8}, at) == dt.datetime(
        2026, 1, 31, 8, tzinfo=UTC
    )
    assert next_run({"frequence": "mensuelle", "jour": 5, "heure": 6}, at) == dt.datetime(
        2026, 2, 5, 6, tzinfo=UTC
    )
    dec = dt.datetime(2026, 12, 20, tzinfo=UTC)
    assert next_run({"frequence": "mensuelle", "jour": 1}, dec) == dt.datetime(
        2027, 1, 1, 6, tzinfo=UTC
    )


def test_dat29_planification_et_alerte(client, ctx, db):  # noqa: F811
    da = ctx["da"].headers
    ds = make_dataset(db, ctx["mission"]["id"], pl.DataFrame({"m": [1, 1, 2]}), "Paiements")
    code = "t = audit.table('Paiements')\naudit.metric('doublons', audit.duplicates(t, ['m']).height)\n"
    s = client.post(f"{ctx['url']}/scripts", headers=da,
                    json={"nom": "Doublons", "code": code, "entrees": [{"type": "table", "id": str(ds.id)}]}).json()  # fmt: skip
    url = f"/api/scripts/{s['id']}/schedule"
    plan = {"frequence": "quotidienne", "heure": 6,
            "alerte": {"indicateur": "doublons", "operateur": ">", "seuil": 0}}  # fmt: skip
    assert (
        client.put(url, json={**plan, "frequence": "hebdomadaire"}, headers=da).status_code == 422
    )
    planned = client.put(url, json=plan, headers=da).json()
    assert planned["planification"]["alerte"]["seuil"] == 0 and planned["prochaine_execution"]
    assert run_due(db) == 0  # échéance future
    script = db.get(Script, s["id"])
    script.prochaine_execution = dt.datetime.now(UTC) - dt.timedelta(minutes=1)
    db.commit()
    assert scheduled_scripts() == 1
    db.expire_all()
    assert db.get(Script, s["id"]).prochaine_execution > dt.datetime.now(UTC)
    run = client.get(f"/api/scripts/{s['id']}/runs", headers=da).json()[0]
    assert run["declenchement"] == "planifie" and run["statut"] == "termine"
    assert run["alerte"] == "doublons = 2 (> 0)"
    alerts = db.scalars(select(Notification).where(Notification.type == "alerte_script")).all()
    assert {n.user_id for n in alerts} == {ctx["chef"].user.id, ctx["da"].user.id}
    # Seuil non atteint : pas d'alerte ; indicateur absent : alerte.
    client.put(url, json={**plan, "alerte": {**plan["alerte"], "seuil": 5}}, headers=da)
    script = db.get(Script, s["id"])
    script.prochaine_execution = dt.datetime.now(UTC) - dt.timedelta(minutes=1)
    db.commit()
    run_due(db)
    assert client.get(f"/api/scripts/{s['id']}/runs", headers=da).json()[0]["alerte"] is None
    client.put(url, json={**plan, "alerte": {**plan["alerte"], "indicateur": "autre"}}, headers=da)
    db.expire_all()
    script = db.get(Script, s["id"])
    script.prochaine_execution = dt.datetime.now(UTC) - dt.timedelta(minutes=1)
    db.commit()
    run_due(db)
    assert (
        "non produit" in client.get(f"/api/scripts/{s['id']}/runs", headers=da).json()[0]["alerte"]
    )
    # Mission clôturée : plus d'exécution ; planification retirée.
    from app.models import Engagement

    script = db.get(Script, s["id"])
    script.prochaine_execution = dt.datetime.now(UTC) - dt.timedelta(minutes=1)
    db.get(Engagement, script.engagement_id).statut = "cloturee"
    db.commit()
    assert run_due(db) == 0
    db.get(Engagement, script.engagement_id).statut = "terrain"
    db.commit()
    unplanned = client.delete(url, headers=da).json()
    assert unplanned["planification"] is None and unplanned["prochaine_execution"] is None
