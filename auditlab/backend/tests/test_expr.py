import datetime as dt

import pytest

from app.analytics.expr import FUNCTION_NAMES, ExprError, compile_expression, parse
from app.analytics.store import connect

COLS = {"montant": "decimal", "taux": "decimal", "Fournisseur": "texte", "date_piece": "date",
        "Montant TTC": "decimal", "code": "texte", "et": "texte"}  # fmt: skip


def run(expr, rows="(VALUES (100.0, 0.2, 'SOGECI SARL', DATE '2026-01-31', 120.0, '401', 'x'))"):
    c = compile_expression(expr, COLS)
    cols = '"montant", "taux", "Fournisseur", "date_piece", "Montant TTC", "code", "et"'
    with connect() as con:
        return con.execute(f"SELECT {c.sql} FROM {rows} AS t({cols})", c.params).fetchone()[0]


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("montant * taux", 20),
        ("montant * 0.2 + 1", 21),
        ("-montant + 2 * 3", -94),
        ("(montant - 50) / 2", 25),
        ("montant / 0", None),
        ("[Montant TTC] - montant", 20),
        ('"Montant TTC" > 100', True),
        ("montant >= 100 ET taux < 1", True),
        ("montant > 100 OU NON (taux = 0.2)", False),
        ("montant > 100 or not taux <> 0.2", True),
        ("SI(montant > 50; 'élevé'; 'faible')", "élevé"),
        ("if(montant > 500, 'élevé', 'faible')", "faible"),
        ("Fournisseur CONTIENT 'sarl'", True),
        ("fournisseur & ' / ' & code", "SOGECI SARL / 401"),
        ("code DANS ('401'; '411')", True),
        ("code NON DANS ('401')", False),
        ("code EST VIDE", False),
        ("code EST NON VIDE", True),
        ("Fournisseur COMME 'soge%'", True),
        ("date_piece > #31/12/2025#", True),
        ("date_piece = #2026-01-31#", True),
        ("ANNEE(date_piece) * 100 + MOIS(date_piece)", 202601),
        ("ECART_JOURS(#01/01/2026#; date_piece)", 30),
        ("FINMOIS(DATE(2026; 2; 10))", dt.date(2026, 2, 28)),
        ("ARRONDI(montant / 3; 2)", 33.33),
        ("ARRONDI(montant / 3)", 33),
        ("GAUCHE(code; 2) & DROITE(code; 1)", "401"),
        ("STXT(Fournisseur; 1; 6)", "SOGECI"),
        ("LONGUEUR(SUPPRESPACE('  ab '))", 2),
        ("MAJUSCULE('é') & MINUSCULE('B')", "Éb"),
        ("SIVIDE(VIDE; 3)", 3),
        ("MAXI(1; montant; 7)", 100),
        ("MINI(taux; 1)", 0.2),
        ("ABS(-2) + MOD(7; 3) + PUISSANCE(2; 3) + RACINE(16)", 15),
        ("[et] = 'x' ET VRAI", True),
        ("REMPLACER(code; '4'; 'C')", "C01"),
        ("TEXTE(montant) COMME '100%'", True),
        ("NOMBRE('12,5') EST VIDE", True),
        ("NOMBRE('12.5')", 12.5),
        ("SIMILARITE('SOGECI'; 'SOGECY') > 0.9", True),
        ("'l''état'", "l'état"),
    ],
)
def test_dat06_expressions(expr, expected):
    value = run(expr)
    if isinstance(expected, float) and value is not None:
        assert float(value) == pytest.approx(expected)
    else:
        assert value == expected or (expected is not None and float(value) == expected)


@pytest.mark.parametrize(
    ("expr", "message", "position"),
    [
        ("", "vide", 0),
        ("montant *", "incomplète", 9),
        ("montant ** 2", "attendue", 9),
        ("inconnue + 1", "Colonne inconnue « inconnue »", 0),
        ("SYSTEM('ls')", "Fonction inconnue « SYSTEM »", 0),
        ("SI(montant > 1; 2)", "SI attend 3 argument(s)", 0),
        ("montant @ 2", "Caractère inattendu", 8),
        ("(montant + 1", "« ) » attendu", 12),
        ("date_piece > #32/13/2026#", "Date invalide", 13),
        ("ARRONDI(montant; taux)", "Nombre entier attendu", 17),
        ("montant 2", "Suite de l'expression inattendue", 8),
        ("code EST rien", "« VIDE » attendu", 9),
    ],
)
def test_dat06_erreurs_localisees(expr, message, position):
    with pytest.raises(ExprError) as err:
        compile_expression(expr, COLS)
    assert message in str(err.value)
    assert err.value.position == position


def test_nf05_textes_en_parametres_jamais_dans_la_requete():
    payload = "x'); DROP TABLE t; --"
    c = compile_expression(f"code = '{payload.replace(chr(39), chr(39) * 2)}'", COLS)
    assert payload in c.params
    assert "DROP" not in c.sql
    assert run(f"code = '{payload.replace(chr(39), chr(39) * 2)}'") is False
    # Un nom de colonne n'est accepté que s'il existe ; il est alors cité.
    with pytest.raises(ExprError):
        compile_expression('"code"" FROM x; --"', COLS)
    c = compile_expression("[Montant TTC] + montant", COLS)
    assert '"Montant TTC"' in c.sql and c.colonnes == {"Montant TTC", "montant"}


def test_longueur_et_liste_des_fonctions():
    with pytest.raises(ExprError, match="trop longue"):
        parse("1+" * 2001 + "1")
    assert {"SI", "ANNEE", "CONTIENT", "ARRONDI"} <= set(FUNCTION_NAMES)
