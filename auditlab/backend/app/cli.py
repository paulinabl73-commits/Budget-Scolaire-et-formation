"""Commandes d'exploitation.

python -m app.cli verify-audit-chain
python -m app.cli create-admin --email admin@exemple.org --nom "Admin"
"""

import argparse
import getpass
import os
import sys

import app.audit.listeners  # noqa: F401
from app.audit.chain import verify_chain
from app.audit.listeners import record_event, set_actor
from app.db import SessionLocal
from app.models.user import User
from app.security.passwords import check_password_policy, hash_password
from app.security.roles import Role


def cmd_verify(_: argparse.Namespace) -> int:
    with SessionLocal() as db:
        report = verify_chain(db)
    if report.ok:
        print(f"Chaîne du journal d'audit intègre : {report.entries} entrées vérifiées.")
        return 0
    print(
        f"RUPTURE de la chaîne à l'entrée n° {report.first_broken_seq} ({report.reason}) "
        f"après {report.entries} entrées valides.",
        file=sys.stderr,
    )
    return 1


def cmd_create_admin(args: argparse.Namespace) -> int:
    password = os.environ.get("AUDITLAB_ADMIN_PASSWORD") or getpass.getpass("Mot de passe : ")
    if errors := check_password_policy(password):
        print("Mot de passe trop faible : " + ", ".join(errors), file=sys.stderr)
        return 2
    with SessionLocal() as db:
        if db.query(User).filter(User.email == args.email.lower()).first():
            print("Un utilisateur existe déjà avec cette adresse.")
            return 0
        set_actor(db, None)
        user = User(
            email=args.email.lower(),
            nom=args.nom,
            role=Role.ADMIN.value,
            password_hash=hash_password(password),
            actif=True,
            mfa_enabled=False,
            failed_logins=0,
        )
        db.add(user)
        record_event(db, "bootstrap_admin", object_type="User", details={"email": user.email})
        db.commit()
        print(f"Administrateur créé : {user.email} (double authentification à activer).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="auditlab")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify-audit-chain", help="Vérifie le chaînage du journal d'audit (NF-02)")
    p = sub.add_parser("create-admin", help="Crée le premier administrateur")
    p.add_argument("--email", required=True)
    p.add_argument("--nom", default="Administrateur")
    args = parser.parse_args(argv)
    return {"verify-audit-chain": cmd_verify, "create-admin": cmd_create_admin}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
