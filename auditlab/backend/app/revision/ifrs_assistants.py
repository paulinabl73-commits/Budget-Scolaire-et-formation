"""Assistants de calcul des retraitements IFRS les plus fréquents (IFR-02).

Chaque assistant reçoit ses paramètres, rend le détail du calcul et propose les lignes de
l'écriture de retraitement (IFR-01) ; l'auditeur la crée puis la valide. Les comptes
proposés par défaut sont modifiables ; aucun taux réglementaire (indemnités, impôt) n'est
supposé : il est saisi.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

ZERO = Decimal(0)


class AssistantError(ValueError):
    pass


@dataclass(frozen=True)
class Param:
    nom: str
    type: str  # nombre, entier, texte, compte, liste
    defaut: Any = None


def _d(value: Any, nom: str) -> Decimal:
    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except Exception as exc:  # noqa: BLE001 - message à l'utilisateur
        raise AssistantError(f"{nom} : nombre attendu") from exc


def _line(compte: str, montant: Decimal, libelle: str) -> list[dict[str, Any]]:
    """Ligne au débit si le montant est positif, au crédit sinon ; rien si nul."""
    if montant == 0:
        return []
    side = "debit" if montant > 0 else "credit"
    return [{"compte": compte, "libelle": libelle, side: str(abs(montant))}]


# --- IFRS 16 : contrats de location ------------------------------------------------------------


def ifrs16(p: dict[str, Any], q: Decimal) -> dict[str, Any]:
    rent, years = _d(p["loyer_annuel"], "Loyer annuel"), int(p["duree_annees"])
    rate = _d(p["taux_actualisation"], "Taux d'actualisation") / 100
    elapsed = int(p.get("annees_ecoulees") or 0)
    if years < 1 or rent <= 0 or rate < 0 or not 0 <= elapsed < years:
        raise AssistantError(
            "Durée d'au moins un an, loyer positif, année en cours dans le contrat"
        )
    factor = Decimal(years) if rate == 0 else (1 - (1 + rate) ** -years) / rate
    if p.get("paiement") == "debut":
        factor *= 1 + rate
    pv = (rent * factor).quantize(q, ROUND_HALF_UP)
    liability, table = pv, []
    for year in range(1, years + 1):
        opening = liability
        if p.get("paiement") == "debut":
            interest = ((opening - rent) * rate).quantize(q, ROUND_HALF_UP)
        else:
            interest = (opening * rate).quantize(q, ROUND_HALF_UP)
        principal = rent - interest
        liability = opening - principal
        table.append(
            {
                "annee": year,
                "dette_ouverture": str(opening),
                "interets": str(interest),
                "remboursement": str(principal),
                "dette_cloture": str(liability),
            }
        )
    depreciation = (pv / years).quantize(q, ROUND_HALF_UP)
    row = table[elapsed]
    lines = []
    if elapsed == 0:
        lines += _line(p["compte_droit"], pv, "Droit d'utilisation")
        lines += _line(p["compte_dette"], -pv, "Dette de location")
    else:  # contrat en cours : situation d'ouverture contre capitaux propres (IFRS 16.C5)
        past_dep = depreciation * elapsed
        opening_liab = Decimal(row["dette_ouverture"])
        lines += _line(p["compte_droit"], pv, "Droit d'utilisation")
        lines += _line(p["compte_amortissement"], -past_dep, "Amortissements antérieurs")
        lines += _line(p["compte_dette"], -opening_liab, "Dette de location à l'ouverture")
        lines += _line(
            p["compte_report"],
            opening_liab + past_dep - pv,
            "Effet sur les capitaux propres d'ouverture",
        )
    lines += _line(p["compte_dette"], Decimal(row["remboursement"]), "Remboursement de la dette")
    lines += _line(
        p["compte_interets"], Decimal(row["interets"]), "Intérêts de la dette de location"
    )
    lines += _line(p["compte_loyer"], -rent, "Annulation du loyer")
    lines += _line(p["compte_dotation"], depreciation, "Amortissement du droit d'utilisation")
    lines += _line(p["compte_amortissement"], -depreciation, "Amortissement du droit d'utilisation")
    return {
        "calcul": {
            "valeur_actualisee": str(pv),
            "amortissement_annuel": str(depreciation),
            "annee_en_cours": elapsed + 1,
            "tableau": table,
        },
        "lignes": lines,
        "libelle": "Contrat de location (IFRS 16)",
    }


# --- IAS 19 : indemnités de fin de carrière (unités de crédit projetées) -------------------------


def ias19(p: dict[str, Any], q: Decimal) -> dict[str, Any]:
    rate = _d(p["taux_actualisation"], "Taux d'actualisation") / 100
    growth = _d(p.get("taux_revalorisation") or 0, "Revalorisation") / 100
    turnover = _d(p.get("taux_rotation") or 0, "Rotation") / 100
    months = _d(p["mois_par_annee"], "Mois de salaire par année d'ancienneté")
    retirement = int(p["age_retraite"])
    booked = _d(p.get("provision_comptabilisee") or 0, "Provision comptabilisée")
    total, detail = ZERO, []
    for i, e in enumerate(p.get("salaries") or [], start=1):
        salary, seniority, age = (
            _d(e["salaire_annuel"], "Salaire"),
            _d(e["anciennete"], "Ancienneté"),
            int(e["age"]),
        )
        remaining = max(retirement - age, 0)
        final_seniority = seniority + remaining
        if final_seniority <= 0:
            continue
        final_salary = salary * (1 + growth) ** remaining
        benefit = final_salary / 12 * months * final_seniority
        obligation = (
            benefit
            * seniority
            / final_seniority
            * (1 - turnover) ** remaining
            / (1 + rate) ** remaining
        )
        obligation = obligation.quantize(q, ROUND_HALF_UP)
        total += obligation
        detail.append(
            {
                "salarie": e.get("nom") or str(i),
                "annees_avant_retraite": remaining,
                "indemnite_projetee": str(benefit.quantize(q, ROUND_HALF_UP)),
                "engagement": str(obligation),
            }
        )
    if not detail:
        raise AssistantError("Au moins un salarié attendu")
    gap = total - booked
    lines = _line(p["compte_charge"], gap, "Charge d'indemnités de fin de carrière")
    lines += _line(p["compte_provision"], -gap, "Provision pour indemnités de fin de carrière")
    return {
        "calcul": {
            "engagement": str(total),
            "provision_comptabilisee": str(booked),
            "ecart": str(gap),
            "salaries": detail,
        },
        "lignes": lines,
        "libelle": "Indemnités de fin de carrière (IAS 19)",
    }


# --- IFRS 9 : pertes de crédit attendues ---------------------------------------------------------


def ifrs9(p: dict[str, Any], q: Decimal) -> dict[str, Any]:
    buckets = p.get("tranches") or []
    if not buckets:
        raise AssistantError("Tranches d'ancienneté et taux de perte attendus")
    expected, detail = ZERO, []
    for b in buckets:
        amount, loss = _d(b["montant"], "Montant"), _d(b["taux_perte"], "Taux de perte")
        ecl = (amount * loss / 100).quantize(q, ROUND_HALF_UP)
        expected += ecl
        detail.append(
            {
                "tranche": b.get("libelle", ""),
                "montant": str(amount),
                "taux_perte": str(loss),
                "perte_attendue": str(ecl),
            }
        )
    booked = _d(p.get("depreciation_comptabilisee") or 0, "Dépréciation comptabilisée")
    gap = expected - booked
    lines = _line(p["compte_dotation"], gap, "Pertes de crédit attendues")
    lines += _line(p["compte_depreciation"], -gap, "Dépréciation des créances")
    return {
        "calcul": {
            "pertes_attendues": str(expected),
            "depreciation_comptabilisee": str(booked),
            "ecart": str(gap),
            "tranches": detail,
        },
        "lignes": lines,
        "libelle": "Pertes de crédit attendues sur créances (IFRS 9)",
    }


# --- IAS 16 : approche par composants ------------------------------------------------------------


def ias16(p: dict[str, Any], q: Decimal) -> dict[str, Any]:
    cost = _d(p["cout"], "Coût")
    elapsed = int(p.get("annees_ecoulees") or 0)
    components = p.get("composants") or []
    if not components or sum(_d(c["quote_part"], "Quote-part") for c in components) != 100:
        raise AssistantError("Composants dont les quotes-parts totalisent 100 %")
    year_dep, past_dep, detail = ZERO, ZERO, []
    for c in components:
        base = cost * _d(c["quote_part"], "Quote-part") / 100
        life = int(c["duree"])
        annual = (base / life).quantize(q, ROUND_HALF_UP)
        this_year = annual if elapsed < life else ZERO
        before = annual * min(elapsed, life)
        year_dep += this_year
        past_dep += before
        detail.append(
            {
                "composant": c.get("libelle", ""),
                "base": str(base.quantize(q)),
                "duree": life,
                "dotation": str(this_year),
                "cumul_anterieur": str(before),
            }
        )
    booked_year = _d(p.get("dotation_comptabilisee") or 0, "Dotation comptabilisée")
    booked_past = _d(p.get("cumul_anterieur_comptabilise") or 0, "Cumul antérieur comptabilisé")
    gap_year, gap_past = year_dep - booked_year, past_dep - booked_past
    lines = _line(p["compte_dotation"], gap_year, "Écart de dotation (composants)")
    lines += _line(p["compte_report"], gap_past, "Écart sur amortissements antérieurs")
    lines += _line(
        p["compte_amortissement"], -(gap_year + gap_past), "Amortissements par composants"
    )
    return {
        "calcul": {
            "dotation_ifrs": str(year_dep),
            "dotation_comptabilisee": str(booked_year),
            "cumul_anterieur_ifrs": str(past_dep),
            "composants": detail,
        },
        "lignes": lines,
        "libelle": "Amortissement par composants (IAS 16)",
    }


# --- IAS 12 : impôts différés sur les retraitements ----------------------------------------------


def ias12(p: dict[str, Any], q: Decimal) -> dict[str, Any]:
    """Impôt différé sur les autres retraitements IFRS validés (différences temporelles)."""
    rate = _d(p["taux_impot"], "Taux d'impôt") / 100
    result, equity = (
        _d(p["effet_resultat"], "Effet sur le résultat"),
        _d(p["effet_capitaux"], "Effet sur les capitaux propres"),
    )
    tax_result = (-result * rate).quantize(q, ROUND_HALF_UP)  # économie d'impôt si charge
    tax_equity = (-(equity - result) * rate).quantize(q, ROUND_HALF_UP)
    total = tax_result + tax_equity
    lines = _line(p["compte_actif"] if total > 0 else p["compte_passif"], total, "Impôt différé")
    lines += _line(p["compte_impot"], -tax_result, "Impôt différé en résultat")
    lines += _line(p["compte_report"], -tax_equity, "Impôt différé en capitaux propres")
    return {
        "calcul": {
            "base_resultat": str(result),
            "base_capitaux": str(equity - result),
            "impot_differe": str(total),
        },
        "lignes": lines,
        "libelle": "Impôts différés sur retraitements (IAS 12)",
    }


# --- IFRS 15 : reconnaissance du revenu ----------------------------------------------------------


def ifrs15(p: dict[str, Any], q: Decimal) -> dict[str, Any]:
    price = _d(p["prix_contrat"], "Prix du contrat")
    obligations = p.get("obligations") or []
    standalone = sum(
        (_d(o["prix_vente_spontane"], "Prix de vente spontané") for o in obligations), ZERO
    )
    if not obligations or standalone <= 0:
        raise AssistantError("Obligations de prestation avec leur prix de vente spontané")
    revenue, detail = ZERO, []
    for o in obligations:
        allocated = price * _d(o["prix_vente_spontane"], "Prix") / standalone
        done = _d(o["pct_execution"], "Avancement") / 100
        recognised = (allocated * done).quantize(q, ROUND_HALF_UP)
        revenue += recognised
        detail.append(
            {
                "obligation": o.get("libelle", ""),
                "prix_alloue": str(allocated.quantize(q, ROUND_HALF_UP)),
                "avancement": str(o["pct_execution"]),
                "produit": str(recognised),
            }
        )
    booked = _d(p["produit_comptabilise"], "Produit comptabilisé")
    gap = revenue - booked
    if gap >= 0:
        lines = _line(p["compte_a_recevoir"], gap, "Produit à reconnaître (actif sur contrat)")
    else:
        lines = _line(
            p["compte_constate_avance"], gap, "Produit constaté d'avance (passif sur contrat)"
        )
    lines += _line(p["compte_produit"], -gap, "Chiffre d'affaires")
    return {
        "calcul": {
            "produit_ifrs": str(revenue),
            "produit_comptabilise": str(booked),
            "ecart": str(gap),
            "obligations": detail,
        },
        "lignes": lines,
        "libelle": "Reconnaissance du revenu (IFRS 15)",
    }


ASSISTANTS: dict[str, dict[str, Any]] = {
    "ifrs16": {
        "norme": "IFRS 16",
        "calcul": ifrs16,
        "params": [
            Param("loyer_annuel", "nombre"),
            Param("duree_annees", "entier"),
            Param("taux_actualisation", "nombre"),
            Param("paiement", "texte", "fin"),
            Param("annees_ecoulees", "entier", 0),
            Param("compte_droit", "compte", "231000"),
            Param("compte_amortissement", "compte", "283100"),
            Param("compte_dette", "compte", "172000"),
            Param("compte_interets", "compte", "671000"),
            Param("compte_loyer", "compte", "622000"),
            Param("compte_dotation", "compte", "681300"),
            Param("compte_report", "compte", "121000"),
        ],
    },
    "ias19": {
        "norme": "IAS 19",
        "calcul": ias19,
        "params": [
            Param("taux_actualisation", "nombre"),
            Param("taux_revalorisation", "nombre", 0),
            Param("taux_rotation", "nombre", 0),
            Param("mois_par_annee", "nombre"),
            Param("age_retraite", "entier"),
            Param("provision_comptabilisee", "nombre", 0),
            Param("salaries", "liste"),
            Param("compte_charge", "compte", "661000"),
            Param("compte_provision", "compte", "196000"),
        ],
    },
    "ifrs9": {
        "norme": "IFRS 9",
        "calcul": ifrs9,
        "params": [
            Param("tranches", "liste"),
            Param("depreciation_comptabilisee", "nombre", 0),
            Param("compte_dotation", "compte", "691000"),
            Param("compte_depreciation", "compte", "491000"),
        ],
    },
    "ias16": {
        "norme": "IAS 16",
        "calcul": ias16,
        "params": [
            Param("cout", "nombre"),
            Param("annees_ecoulees", "entier", 0),
            Param("composants", "liste"),
            Param("dotation_comptabilisee", "nombre", 0),
            Param("cumul_anterieur_comptabilise", "nombre", 0),
            Param("compte_dotation", "compte", "681300"),
            Param("compte_amortissement", "compte", "283100"),
            Param("compte_report", "compte", "121000"),
        ],
    },
    "ias12": {
        "norme": "IAS 12",
        "calcul": ias12,
        "params": [
            Param("taux_impot", "nombre"),
            Param("effet_resultat", "nombre"),
            Param("effet_capitaux", "nombre"),
            Param("compte_actif", "compte", "449800"),
            Param("compte_passif", "compte", "449900"),
            Param("compte_impot", "compte", "891000"),
            Param("compte_report", "compte", "121000"),
        ],
    },
    "ifrs15": {
        "norme": "IFRS 15",
        "calcul": ifrs15,
        "params": [
            Param("prix_contrat", "nombre"),
            Param("obligations", "liste"),
            Param("produit_comptabilise", "nombre"),
            Param("compte_produit", "compte", "701100"),
            Param("compte_a_recevoir", "compte", "418100"),
            Param("compte_constate_avance", "compte", "477000"),
        ],
    },
}


def run(code: str, params: dict[str, Any], q: Decimal) -> dict[str, Any]:
    if code not in ASSISTANTS:
        raise AssistantError("Assistant inconnu")
    spec = ASSISTANTS[code]
    values = {p.nom: params.get(p.nom, p.defaut) for p in spec["params"]}
    missing = [k for k, v in values.items() if v in (None, "")]
    if missing:
        raise AssistantError(f"Paramètre manquant : {missing[0]}")
    try:
        out = spec["calcul"](values, q)
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        if isinstance(exc, AssistantError):
            raise
        raise AssistantError(f"Paramètres invalides : {exc}") from exc
    return {"norme": spec["norme"], **out}
