import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, post } from "../../api/client";
import type { Dataset } from "../../api/types";
import { formatDateHeure, formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Side {
  erreurs: number;
  erreur_lignes_superieures: string;
  erreur_projetee: string;
  precision_de_base: string;
  provision_supplementaire: string;
  limite_superieure: string;
}

interface Evaluation {
  id: string;
  confiance: string;
  erreur_tolerable: string | null;
  erreurs: { ligne: number; montant_comptable: string; montant_audite: string; ecart: string; commentaire: string | null }[];
  resultat: { intervalle: string; surevaluations: Side; sous_evaluations: Side; conclusion?: string };
  created_at: string | null;
}

const num = (v: string) => v.replace(/\s/g, "").replace(",", ".");
const money = (v: string) => formatNombre(Number(v));

/** Évaluation d'un échantillon MUS (DAT-23) : erreurs constatées, projection, limite supérieure. */
export default function MusEvaluation({ ds, canEdit }: { ds: Dataset; canEdit: boolean }) {
  const { t } = useTranslation();
  const [list, setList] = useState<Evaluation[]>([]);
  const [confiance, setConfiance] = useState("95");
  const [tolerable, setTolerable] = useState("");
  const [rows, setRows] = useState<{ ligne: string; audite: string; commentaire: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const url = `/datasets/${ds.id}/mus-evaluations`;
  const load = useCallback(() => api<Evaluation[]>(url).then(setList), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await post(url, {
        confiance: String(Number(num(confiance)) / 100),
        erreur_tolerable: tolerable ? num(tolerable) : null,
        erreurs: rows.map((r) => ({ ligne: Number(r.ligne), montant_audite: num(r.audite), commentaire: r.commentaire || null })),
      });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const last = list[0];
  const sides: [string, Side][] = last ? [[t("mus.surevaluations"), last.resultat.surevaluations], [t("mus.sousEvaluations"), last.resultat.sous_evaluations]] : [];
  return (
    <section className="carte space-y-3" aria-labelledby="mus-titre">
      <h2 id="mus-titre" className="text-base font-semibold">{t("mus.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {canEdit && (
        <form onSubmit={submit} className="space-y-2">
          <div className="grid gap-2 md:grid-cols-3">
            <div>
              <label htmlFor="mus-conf" className="etiquette">{t("taille.confiance")}</label>
              <input id="mus-conf" className="champ" inputMode="decimal" value={confiance} onChange={(e) => setConfiance(e.target.value)} />
            </div>
            <div>
              <label htmlFor="mus-tol" className="etiquette">{t("taille.tolerable")}</label>
              <input id="mus-tol" className="champ" inputMode="decimal" value={tolerable} onChange={(e) => setTolerable(e.target.value)} />
            </div>
          </div>
          <fieldset className="space-y-1">
            <legend className="etiquette">{t("mus.erreurs")}</legend>
            {rows.map((r, i) => (
              <div key={i} className="flex flex-wrap gap-2">
                <input aria-label={t("mus.ligne")} placeholder={t("mus.ligne")} className="champ mt-0 w-28" inputMode="numeric" required value={r.ligne}
                  onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, ligne: e.target.value } : x)))} />
                <input aria-label={t("mus.audite")} placeholder={t("mus.audite")} className="champ mt-0 w-40" inputMode="decimal" required value={r.audite}
                  onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, audite: e.target.value } : x)))} />
                <input aria-label={t("mus.commentaire")} placeholder={t("mus.commentaire")} className="champ mt-0 flex-1" value={r.commentaire}
                  onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, commentaire: e.target.value } : x)))} />
                <button type="button" className="text-sm text-red-700 underline" onClick={() => setRows(rows.filter((_, j) => j !== i))}>{t("analyses.retirer")}</button>
              </div>
            ))}
            <button type="button" className="text-sm text-marque-700 underline" onClick={() => setRows([...rows, { ligne: "", audite: "", commentaire: "" }])}>
              {t("mus.ajouterErreur")}
            </button>
          </fieldset>
          <button type="submit" className="btn-primaire">{t("mus.evaluer")}</button>
        </form>
      )}
      {last && (
        <div className="space-y-2 border-t border-slate-100 pt-2">
          <p className="text-sm text-slate-600">
            {t("mus.du", { date: formatDateHeure(last.created_at) })} · {t("mus.intervalle", { i: money(last.resultat.intervalle) })} · {t("mus.confiance", { c: formatNombre(Number(last.confiance) * 100) })}
          </p>
          <table className="w-full text-right text-sm">
            <thead className="text-xs text-slate-600">
              <tr>
                <th scope="col" className="text-left">{t("mus.sens")}</th>
                <th scope="col">{t("mus.nb")}</th>
                <th scope="col">{t("mus.projetee")}</th>
                <th scope="col">{t("mus.base")}</th>
                <th scope="col">{t("mus.provision")}</th>
                <th scope="col">{t("mus.limite")}</th>
              </tr>
            </thead>
            <tbody>
              {sides.map(([label, s]) => (
                <tr key={label}>
                  <th scope="row" className="text-left font-normal">{label}</th>
                  <td>{s.erreurs}</td>
                  <td className="font-mono">{money(s.erreur_projetee)}</td>
                  <td className="font-mono">{money(s.precision_de_base)}</td>
                  <td className="font-mono">{money(s.provision_supplementaire)}</td>
                  <td className="font-mono font-semibold">{money(s.limite_superieure)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {last.resultat.conclusion && (
            <Alert kind={last.resultat.conclusion === "acceptable" ? "succes" : "erreur"}>
              {t(`mus.conclusions.${last.resultat.conclusion}`, { tolerable: money(last.erreur_tolerable ?? "0"), limite: money(last.resultat.surevaluations.limite_superieure) })}
            </Alert>
          )}
        </div>
      )}
    </section>
  );
}
