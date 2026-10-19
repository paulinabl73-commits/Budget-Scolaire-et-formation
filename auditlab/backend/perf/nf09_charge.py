"""NF-09 : pages métier affichées en moins d'une seconde pour 50 utilisateurs simultanés.

Chaque utilisateur virtuel ouvre en boucle des pages métier ; une page est l'ensemble des
appels que l'écran lance en parallèle (comme le navigateur). Mesure : durée d'une page, du
premier appel à la dernière réponse ; objectif : 95e centile < 1 s.

    python perf/nf09_charge.py --url http://127.0.0.1:8000 --utilisateurs 50 --duree 60 \
        --compte chef@auditlab.local:Mot-de-passe-2026
"""

import argparse
import asyncio
import random
import statistics
import time

import httpx


def pages(mission: str, dataset: str | None) -> dict[str, list[str]]:
    m = f"/api/engagements/{mission}"
    out = {
        "Accueil": ["/api/auth/me", "/api/me/notifications", "/api/engagements"],
        "Mission": [m, f"/api/dashboards/missions/{mission}", f"{m}/findings", f"{m}/workpapers"],
        "Constats": [f"{m}/findings", f"{m}/action-plans"],
        "Temps": [f"{m}/time-summary", f"{m}/time-entries"],
        "Données": [f"{m}/datasets"],
    }
    if dataset:
        rows = ("POST", f"/api/datasets/{dataset}/rows", {"offset": 0, "limit": 100})
        out["Grille"] = [f"/api/datasets/{dataset}", rows]
    return out


async def call(client: httpx.AsyncClient, c: str | tuple, headers: dict) -> int:
    """Un appel ; une connexion fermée par le serveur pendant sa réutilisation est reprise une
    fois (fermeture des connexions inactives), une seconde erreur compte comme un échec."""
    for attempt in range(2):
        try:
            if isinstance(c, str):
                response = await client.get(c, headers=headers)
            else:
                response = await client.request(c[0], c[1], json=c[2], headers=headers)
            return response.status_code
        except httpx.TransportError:
            if attempt:
                return 599
    return 599


async def user(
    client: httpx.AsyncClient,
    token: str,
    catalog: dict,
    warm: float,
    stop: float,
    out: list,
    pause: float,
) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    names = list(catalog)
    while time.perf_counter() < stop:
        name = random.choice(names)
        start = time.perf_counter()
        responses = await asyncio.gather(*(call(client, c, headers) for c in catalog[name]))
        elapsed = time.perf_counter() - start
        errors = [r for r in responses if r >= 400]
        if start >= warm:  # mesures après l'échauffement seulement
            out.append((name, elapsed, errors))
        await asyncio.sleep(random.uniform(0.5, 1.5) * pause)  # temps de lecture de l'écran


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--utilisateurs", type=int, default=50)
    parser.add_argument("--duree", type=int, default=60)
    parser.add_argument("--compte", required=True, help="adresse:mot de passe")
    parser.add_argument("--mission")
    parser.add_argument("--table")
    parser.add_argument("--echauffement", type=int, default=15, help="durée non mesurée (s)")
    parser.add_argument("--pause", type=float, default=5.0, help="temps de lecture moyen (s)")
    args = parser.parse_args()
    email, password = args.compte.split(":", 1)
    limits = httpx.Limits(max_connections=args.utilisateurs * 4)
    async with httpx.AsyncClient(base_url=args.url, timeout=30, limits=limits) as client:
        login = await client.post("/api/auth/login", json={"email": email, "password": password})
        login.raise_for_status()
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        mission = (
            args.mission or (await client.get("/api/engagements", headers=headers)).json()[0]["id"]
        )
        catalog = pages(mission, args.table)
        results: list = []
        warm = time.perf_counter() + args.echauffement
        stop = warm + args.duree
        await asyncio.gather(
            *(user(client, token, catalog, warm, stop, results, args.pause)
              for _ in range(args.utilisateurs))
        )  # fmt: skip
    durations = sorted(r[1] for r in results)
    p95 = durations[int(len(durations) * 0.95) - 1]
    errors = [r for r in results if r[2]]
    print(
        f"{args.utilisateurs} utilisateurs, {args.duree} s, lecture {args.pause} s : "
        f"{len(results)} pages ({len(results) / args.duree:.1f}/s), {len(errors)} en erreur"
    )
    median = statistics.median(durations)
    print(f"médiane {median:.3f} s ; 95e centile {p95:.3f} s ; max {durations[-1]:.3f} s")
    for name in catalog:
        own = sorted(r[1] for r in results if r[0] == name)
        if own:
            print(f"  {name:10s} n={len(own):5d} p95={own[int(len(own) * 0.95) - 1]:.3f} s")
    print("OBJECTIF ATTEINT" if p95 < 1 and not errors else "OBJECTIF NON ATTEINT")


if __name__ == "__main__":
    asyncio.run(main())
