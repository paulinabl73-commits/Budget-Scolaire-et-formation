"""Lanceur exécuté dans le bac à sable : `python bootstrap.py <répertoire de travail>`.

Ne dépend que de la bibliothèque standard, de polars et du module `audit` placé à côté ; le
script de l'utilisateur est `script.py` du répertoire de travail. Une erreur est écrite dans
`out/erreur.txt` (trace limitée au script de l'utilisateur).
"""

import sys
import traceback
from pathlib import Path


def main() -> int:
    work = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(Path(__file__).resolve().parent / "sdk"))
    import audit

    audit._init(work)
    (work / "out").mkdir(exist_ok=True)
    audit._flush()
    source = (work / "script.py").read_text("utf-8")
    try:
        code = compile(source, "script.py", "exec")
        exec(code, {"__name__": "__main__", "audit": audit})  # noqa: S102 (bac à sable)
    except audit.AuditError as exc:
        (work / "out" / "erreur.txt").write_text(str(exc), "utf-8")
        return 1
    except BaseException as exc:  # noqa: BLE001
        frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == "script.py"]
        lines = traceback.format_list(frames) + traceback.format_exception_only(exc)
        (work / "out" / "erreur.txt").write_text("".join(lines)[-5000:], "utf-8")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
