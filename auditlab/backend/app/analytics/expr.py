"""Expressions saisies par les utilisateurs (DAT-06 champs calculés, DAT-09 extraction).

L'expression est analysée par une grammaire fermée, puis compilée en SQL DuckDB :
- les noms de colonnes sont vérifiés dans le schéma de la table, puis cités ;
- les textes et les dates sont passés en paramètres (NF-05) ;
- les nombres sont réécrits à partir de leur valeur analysée ;
- seules les fonctions de la liste ci-dessous sont acceptées.
Aucun fragment du texte saisi n'est donc recopié tel quel dans la requête.

Syntaxe (mots-clés en français ou en anglais, sans distinction de casse) :
    montant * taux                       [Montant TTC] - [Montant HT]
    SI(montant > 1000; 'élevé'; 'faible')  date_piece > #31/12/2024#
    fournisseur CONTIENT 'SARL' ET NON (montant EST VIDE)
    code DANS ('401'; '411')             nom & ' ' & prenom
Les arguments se séparent par « ; » (usage français) ou « , ».
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.analytics.store import quote_ident


class ExprError(ValueError):
    """Expression invalide ; `position` indique le caractère fautif (0 = début)."""

    def __init__(self, message: str, position: int = 0) -> None:
        super().__init__(message)
        self.position = position


# --- Analyse lexicale -------------------------------------------------------------------------

_TOKEN = re.compile(
    r"""
    (?P<espace>\s+)
  | (?P<date>\#[^#]*\#)
  | (?P<nombre>\d+(?:\.\d+)?)
  | (?P<texte>'(?:[^']|'')*')
  | (?P<colonne>\[[^\]]+\]|"(?:[^"]|"")+")
  | (?P<op><>|!=|<=|>=|==|[=<>+\-*/%&(),;])
  | (?P<mot>[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]*)
    """,
    re.VERBOSE,
)


@dataclass
class Token:
    kind: str
    value: Any
    pos: int


_KEYWORDS = {
    "et": "ET", "and": "ET",
    "ou": "OU", "or": "OU",
    "non": "NON", "not": "NON",
    "contient": "CONTIENT", "contains": "CONTIENT",
    "dans": "DANS", "in": "DANS",
    "est": "EST", "is": "EST",
    "vide": "VIDE", "null": "VIDE", "nul": "VIDE",
    "vrai": "VRAI", "true": "VRAI",
    "faux": "FAUX", "false": "FAUX",
    "comme": "COMME", "like": "COMME",
}  # fmt: skip

_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d")


def _parse_date(raw: str, pos: int) -> dt.date:
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise ExprError(f"Date invalide « {raw} » (attendu jj/mm/aaaa ou aaaa-mm-jj)", pos)


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            raise ExprError(f"Caractère inattendu « {text[pos]} »", pos)
        kind, raw = m.lastgroup, m.group()
        if kind == "nombre":
            tokens.append(Token("nombre", Decimal(raw), pos))
        elif kind == "texte":
            tokens.append(Token("texte", raw[1:-1].replace("''", "'"), pos))
        elif kind == "date":
            tokens.append(Token("date", _parse_date(raw[1:-1], pos), pos))
        elif kind == "colonne":
            name = raw[1:-1] if raw.startswith("[") else raw[1:-1].replace('""', '"')
            tokens.append(Token("colonne", name, pos))
        elif kind == "op":
            tokens.append(Token("op", {"==": "=", "!=": "<>", ",": ";"}.get(raw, raw), pos))
        elif kind == "mot":
            kw = _KEYWORDS.get(raw.lower())
            tokens.append(Token("mot", kw, pos) if kw else Token("nom", raw, pos))
        pos = m.end()
    tokens.append(Token("fin", None, len(text)))
    return tokens


# --- Arbre syntaxique -------------------------------------------------------------------------


@dataclass
class Node:
    kind: str  # litteral, colonne, unaire, binaire, fonction, dans, est_vide
    value: Any = None
    children: list["Node"] = field(default_factory=list)
    pos: int = 0


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.i = 0

    @property
    def tok(self) -> Token:
        return self.tokens[self.i]

    def eat(self, kind: str, value: Any = None) -> Token | None:
        t = self.tok
        if t.kind == kind and (value is None or t.value == value):
            self.i += 1
            return t
        return None

    def expect(self, kind: str, value: Any, label: str) -> Token:
        t = self.eat(kind, value)
        if t is None:
            raise ExprError(f"« {label} » attendu", self.tok.pos)
        return t

    def parse(self) -> Node:
        if self.tok.kind == "fin":
            raise ExprError("Expression vide", 0)
        node = self.or_()
        if self.tok.kind != "fin":
            raise ExprError("Suite de l'expression inattendue", self.tok.pos)
        return node

    def or_(self) -> Node:
        node = self.and_()
        while t := self.eat("mot", "OU"):
            node = Node("binaire", "OR", [node, self.and_()], t.pos)
        return node

    def and_(self) -> Node:
        node = self.not_()
        while t := self.eat("mot", "ET"):
            node = Node("binaire", "AND", [node, self.not_()], t.pos)
        return node

    def not_(self) -> Node:
        if t := self.eat("mot", "NON"):
            return Node("unaire", "NOT", [self.not_()], t.pos)
        return self.comparison()

    def comparison(self) -> Node:
        node = self.additive()
        t = self.tok
        if t.kind == "op" and t.value in ("=", "<>", "<", "<=", ">", ">="):
            self.i += 1
            return Node("binaire", t.value, [node, self.additive()], t.pos)
        if self.eat("mot", "CONTIENT"):
            return Node("fonction", "contient", [node, self.additive()], t.pos)
        if self.eat("mot", "COMME"):
            return Node("binaire", "ILIKE", [node, self.additive()], t.pos)
        negate = False
        if t.kind == "mot" and t.value == "NON" and self.tokens[self.i + 1].value == "DANS":
            self.i += 1
            negate = True
        if self.eat("mot", "DANS"):
            self.expect("op", "(", "(")
            items = [self.additive()]
            while self.eat("op", ";"):
                items.append(self.additive())
            self.expect("op", ")", ")")
            return Node("dans", negate, [node, *items], t.pos)
        if self.eat("mot", "EST"):
            negate = bool(self.eat("mot", "NON"))
            self.expect("mot", "VIDE", "VIDE")
            return Node("est_vide", negate, [node], t.pos)
        return node

    def additive(self) -> Node:
        node = self.multiplicative()
        while self.tok.kind == "op" and self.tok.value in ("+", "-", "&"):
            t = self.tok
            self.i += 1
            node = Node("binaire", t.value, [node, self.multiplicative()], t.pos)
        return node

    def multiplicative(self) -> Node:
        node = self.unary()
        while self.tok.kind == "op" and self.tok.value in ("*", "/", "%"):
            t = self.tok
            self.i += 1
            node = Node("binaire", t.value, [node, self.unary()], t.pos)
        return node

    def unary(self) -> Node:
        if t := self.eat("op", "-"):
            return Node("unaire", "-", [self.unary()], t.pos)
        return self.primary()

    def primary(self) -> Node:
        t = self.tok
        if t.kind in ("nombre", "texte", "date"):
            self.i += 1
            return Node("litteral", t.value, pos=t.pos)
        if t.kind == "mot" and t.value in ("VRAI", "FAUX", "VIDE"):
            self.i += 1
            return Node("litteral", {"VRAI": True, "FAUX": False, "VIDE": None}[t.value], pos=t.pos)
        if t.kind == "colonne":
            self.i += 1
            return Node("colonne", t.value, pos=t.pos)
        if t.kind == "nom":
            self.i += 1
            if self.eat("op", "("):
                args: list[Node] = []
                if not self.eat("op", ")"):
                    args.append(self.or_())
                    while self.eat("op", ";"):
                        args.append(self.or_())
                    self.expect("op", ")", ")")
                return Node("fonction", t.value.lower(), args, t.pos)
            return Node("colonne", t.value, pos=t.pos)
        if self.eat("op", "("):
            node = self.or_()
            self.expect("op", ")", ")")
            return node
        if t.kind == "fin":
            raise ExprError("Expression incomplète", t.pos)
        raise ExprError("Valeur, colonne ou fonction attendue", t.pos)


def parse(text: str) -> Node:
    if len(text) > 4000:
        raise ExprError("Expression trop longue (4 000 caractères au plus)")
    return _Parser(tokenize(text)).parse()


# --- Fonctions --------------------------------------------------------------------------------

# nom accepté → (nom canonique, nombre d'arguments min, max, gabarit SQL)
# Le gabarit reçoit les arguments compilés {0}, {1}… ; « * » = liste variable.
_FUNCTIONS: dict[str, tuple[str, int, int, str]] = {}


def _fn(names: str, nmin: int, nmax: int, template: str) -> None:
    canonical = names.split()[0].upper()
    for name in names.split():
        _FUNCTIONS[name] = (canonical, nmin, nmax, template)


_fn("si if", 3, 3, "CASE WHEN {0} THEN {1} ELSE {2} END")
_fn("sivide coalesce", 2, 2, "coalesce({0}, {1})")
_fn("abs", 1, 1, "abs({0})")
_fn("arrondi round", 1, 2, "round({0}, {1:int})")
_fn("ent int plancher floor", 1, 1, "floor({0})")
_fn("plafond ceil", 1, 1, "ceil({0})")
_fn("racine sqrt", 1, 1, "sqrt({0})")
_fn("puissance power", 2, 2, "power({0}, {1})")
_fn("log10", 1, 1, "log10({0})")
_fn("ln", 1, 1, "ln({0})")
_fn("mod", 2, 2, "({0} % {1})")
_fn("mini least", 2, 9, "least(*)")
_fn("maxi greatest", 2, 9, "greatest(*)")
_fn("annee year", 1, 1, "year({0})")
_fn("mois month", 1, 1, "month({0})")
_fn("jour day", 1, 1, "day({0})")
_fn("joursem weekday", 1, 1, "isodow({0})")
_fn("trimestre quarter", 1, 1, "quarter({0})")
_fn("finmois eomonth", 1, 1, "last_day({0})")
_fn("date", 3, 3, "make_date(CAST({0} AS INTEGER), CAST({1} AS INTEGER), CAST({2} AS INTEGER))")
_fn("ecart_jours datediff", 2, 2, "date_diff('day', {0}, {1})")
_fn("majuscule upper", 1, 1, "upper({0})")
_fn("minuscule lower", 1, 1, "lower({0})")
_fn("supprespace trim", 1, 1, "trim({0})")
_fn("longueur len length", 1, 1, "length({0})")
_fn("gauche left", 2, 2, "left({0}, {1:int})")
_fn("droite right", 2, 2, "right({0}, {1:int})")
_fn("stxt substr mid", 3, 3, "substr({0}, {1:int}, {2:int})")
_fn("remplacer replace", 3, 3, "replace({0}, {1}, {2})")
_fn("contient contains", 2, 2, "contains(lower(CAST({0} AS VARCHAR)), lower({1}))")
_fn("commence startswith", 2, 2, "starts_with(CAST({0} AS VARCHAR), {1})")
_fn("texte str", 1, 1, "CAST({0} AS VARCHAR)")
_fn("nombre num", 1, 1, "TRY_CAST({0} AS DOUBLE)")
_fn("estvide isnull", 1, 1, "({0} IS NULL)")
_fn("similarite similarity", 2, 2, "jaro_winkler_similarity(lower({0}), lower({1}))")
_fn("soundex", 1, 1, "soundex({0})")

FUNCTION_NAMES = sorted({v[0] for v in _FUNCTIONS.values()})


# --- Compilation ------------------------------------------------------------------------------


@dataclass
class Compiled:
    sql: str
    params: list[Any]
    colonnes: set[str]


class _Compiler:
    def __init__(self, columns: dict[str, str]) -> None:
        # Recherche des colonnes sans distinction de casse, nom exact prioritaire.
        self.columns = columns
        self.lower = {c.lower(): c for c in columns}
        self.params: list[Any] = []
        self.used: set[str] = set()

    def column(self, node: Node) -> str:
        name = node.value if node.value in self.columns else self.lower.get(node.value.lower())
        if name is None:
            raise ExprError(f"Colonne inconnue « {node.value} »", node.pos)
        self.used.add(name)
        return quote_ident(name)

    def literal(self, value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, Decimal):
            # Réécrit depuis la valeur analysée : aucun texte saisi n'atteint la requête.
            return format(value, "f")
        self.params.append(value)
        return "CAST(? AS DATE)" if isinstance(value, dt.date) else "CAST(? AS VARCHAR)"

    def int_arg(self, node: Node) -> str:
        if node.kind == "unaire" and node.value == "-":
            return f"-{self.int_arg(node.children[0])}"
        if node.kind != "litteral" or not isinstance(node.value, Decimal):
            raise ExprError("Nombre entier attendu", node.pos)
        try:
            return str(int(node.value))
        except (InvalidOperation, ValueError) as exc:  # pragma: no cover - Decimal toujours fini
            raise ExprError("Nombre entier attendu", node.pos) from exc

    def compile(self, node: Node) -> str:
        if node.kind == "litteral":
            return self.literal(node.value)
        if node.kind == "colonne":
            return self.column(node)
        if node.kind == "unaire":
            inner = self.compile(node.children[0])
            return f"(NOT {inner})" if node.value == "NOT" else f"(-{inner})"
        if node.kind == "binaire":
            left, right = (self.compile(c) for c in node.children)
            if node.value == "&":
                left, right = (f"coalesce(CAST({x} AS VARCHAR), '')" for x in (left, right))
                return f"({left} || {right})"
            if node.value == "/":
                # Division décimale ; une division par zéro donne une valeur vide.
                return f"(CAST({left} AS DOUBLE) / NULLIF(CAST({right} AS DOUBLE), 0))"
            return f"({left} {node.value} {right})"
        if node.kind == "dans":
            target, *items = (self.compile(c) for c in node.children)
            op = "NOT IN" if node.value else "IN"
            return f"({target} {op} ({', '.join(items)}))"
        if node.kind == "est_vide":
            inner = self.compile(node.children[0])
            return f"({inner} IS {'NOT ' if node.value else ''}NULL)"
        return self.function(node)

    def function(self, node: Node) -> str:
        spec = _FUNCTIONS.get(node.value)
        if spec is None:
            raise ExprError(f"Fonction inconnue « {node.value.upper()} »", node.pos)
        canonical, nmin, nmax, template = spec
        args = node.children
        if not nmin <= len(args) <= nmax:
            count = str(nmin) if nmin == nmax else f"{nmin} à {nmax}"
            raise ExprError(f"{canonical} attend {count} argument(s)", node.pos)
        if "*" in template:
            return template.replace("*", ", ".join(self.compile(a) for a in args))
        if canonical == "ARRONDI" and len(args) == 1:
            args = [*args, Node("litteral", Decimal(0))]

        def render(m: re.Match[str]) -> str:
            index, kind = int(m.group(1)), m.group(2)
            return self.int_arg(args[index]) if kind else self.compile(args[index])

        return re.sub(r"\{(\d)(:int)?\}", render, template)


def compile_expression(text: str, columns: dict[str, str]) -> Compiled:
    """Compile une expression pour une table dont `columns` donne les noms et types."""
    compiler = _Compiler(columns)
    sql = compiler.compile(parse(text))
    return Compiled(sql, compiler.params, compiler.used)
