"""Jeu de référence du Module 5 : une société commerciale en SYSCOHADA (montants en FCFA).

Calculs de contrôle (exercice N) : total du bilan 31 700 000, chiffre d'affaires 40 000 000,
résultat net 7 100 000 ; exercice N-1 : résultat 1 500 000, affecté en report à nouveau.
"""

import io
from decimal import Decimal

from openpyxl import Workbook

LIBELLES = {
    "101300": "Capital souscrit, appelé, versé", "111000": "Réserve légale",
    "121000": "Report à nouveau créditeur", "162000": "Emprunts auprès des établissements de crédit",
    "244400": "Matériel de bureau", "284400": "Amortissements du matériel de bureau",
    "245100": "Matériel automobile", "284510": "Amortissements du matériel automobile",
    "311000": "Marchandises", "401100": "Fournisseurs", "401200": "Fournisseur Alpha (débiteur)",
    "411100": "Clients", "419100": "Clients, avances reçues", "421000": "Personnel, rémunérations dues",
    "441000": "État, impôt sur les bénéfices", "521100": "Banque Atlantique", "521200": "Banque BICICI",
    "571100": "Caisse siège", "601100": "Achats de marchandises",
    "603100": "Variation des stocks de marchandises", "622000": "Locations", "641000": "Impôts et taxes",
    "661000": "Rémunérations du personnel", "671000": "Intérêts des emprunts",
    "681300": "Dotations aux amortissements", "701100": "Ventes de marchandises",
    "891000": "Impôts sur les bénéfices",
}  # fmt: skip

# Soldes de clôture (débit positif, crédit négatif).
N1 = {
    "101300": -10_000_000, "111000": -1_000_000, "121000": -500_000, "162000": -6_000_000,
    "244400": 5_000_000, "284400": -1_000_000, "245100": 4_000_000, "284510": -500_000,
    "311000": 3_500_000, "401100": -4_000_000, "411100": 6_000_000, "421000": -300_000,
    "441000": -500_000, "521100": 6_600_000, "571100": 200_000,
    "701100": -30_000_000, "601100": 18_000_000, "661000": 5_000_000, "622000": 1_000_000,
    "671000": 500_000, "681300": 1_500_000, "891000": 2_500_000,
}  # fmt: skip
N = {
    "101300": -10_000_000, "111000": -1_000_000, "121000": -2_000_000, "162000": -5_000_000,
    "244400": 6_000_000, "284400": -2_000_000, "245100": 4_000_000, "284510": -1_000_000,
    "311000": 3_000_000, "401100": -4_500_000, "401200": 200_000, "411100": 7_000_000,
    "419100": -300_000, "421000": -400_000, "441000": -600_000, "521100": 14_200_000,
    "521200": -800_000, "571100": 300_000,
    "601100": 20_000_000, "603100": 500_000, "622000": 1_200_000, "641000": 300_000,
    "661000": 6_000_000, "671000": 400_000, "681300": 1_500_000, "701100": -40_000_000,
    "891000": 3_000_000,
}  # fmt: skip
RESULTAT_N1 = 1_500_000


def opening_n() -> dict[str, int]:
    """À-nouveaux N : soldes de bilan N-1, résultat N-1 affecté au report à nouveau."""
    opening = {c: v for c, v in N1.items() if c[0] in "12345"}
    opening["121000"] -= RESULTAT_N1
    return opening


def fr(amount: int | Decimal) -> str:
    """Format français : espace des milliers, virgule décimale."""
    text = f"{Decimal(amount):,.2f}".replace(",", " ").replace(".", ",")
    return text


def split(net: int) -> tuple[int, int]:
    return (net, 0) if net >= 0 else (0, -net)


def rows_n(closing=N, opening=None) -> list[tuple]:  # noqa: B006
    opening = opening if opening is not None else opening_n()
    out = []
    for compte in sorted(set(closing) | set(opening)):
        o, c = opening.get(compte, 0), closing.get(compte, 0)
        out.append((compte, LIBELLES[compte], *split(o), *split(c - o), *split(c)))
    return out


def sage_csv(closing=N, opening=None) -> bytes:  # noqa: B006
    """Balance générale façon Sage : lignes de titre, en-tête, montants français, total, cp1252."""
    lines = ["SOCIETE IVOIRIENNE DE NEGOCE SA;;;;;;;", "Balance générale au 31/12/2026;;;;;;;", ";;;;;;;",
             "N° compte;Intitulé;Solde début débit;Solde début crédit;Mouvements débit;"
             "Mouvements crédit;Solde fin débit;Solde fin crédit"]  # fmt: skip
    rows = rows_n(closing, opening)
    for r in rows:
        lines.append(";".join([r[0], r[1], *(fr(v) if v else "" for v in r[2:])]))
    sums = [sum(r[i] for r in rows) for i in range(2, 8)]
    lines.append(";".join(["", "TOTAL BALANCE", *(fr(v) for v in sums)]))
    return ("\n".join(lines) + "\n").encode("cp1252")


def odoo_xlsx(closing=N1) -> bytes:  # noqa: B006
    """Balance façon Odoo (N-1) : colonnes signées « Solde initial » et « Solde final »."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Balance de vérification"])
    ws.append([])
    ws.append(["Code", "Compte", "Solde initial", "Débit", "Crédit", "Solde final"])
    for compte in sorted(closing):
        c = closing[compte]
        ws.append([int(compte), LIBELLES[compte], 0, max(c, 0), max(-c, 0), c])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def ledger_csv(closing=N, opening=None, skew: dict | None = None) -> bytes:  # noqa: B006
    """Grand livre N : à-nouveaux (journal AN) puis une écriture par compte et par sens."""
    opening = opening if opening is not None else opening_n()
    skew = skew or {}
    lines = ["Date;Journal;N° pièce;Compte;Libellé;Débit;Crédit;Utilisateur"]
    for compte, o in sorted(opening.items()):
        d, c = split(o)
        lines.append(f"01/01/2026;AN;AN-{compte};{compte};À nouveau;{fr(d)};{fr(c)};system")
    piece = 1
    for r in rows_n(closing, opening):
        compte, md, mc = r[0], r[4], r[5]
        md += skew.get(compte, 0)
        if md:
            lines.append(f"15/06/2026;OD;P{piece:04d};{compte};Mouvements;{fr(md)};;kouassi")
            piece += 1
        if mc:
            lines.append(f"15/06/2026;OD;P{piece:04d};{compte};Mouvements;;{fr(mc)};kouassi")
            piece += 1
    return ("\n".join(lines) + "\n").encode("utf-8")
