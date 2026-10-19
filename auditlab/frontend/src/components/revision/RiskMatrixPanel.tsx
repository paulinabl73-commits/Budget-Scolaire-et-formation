import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, post, put } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Cell {
  cycle: string;
  assertion: string;
  risque_inherent: string | null;
  risque_controle: string | null;
  risque_important: boolean;
  commentaire: string | null;
  risque: string | null;
  dans_programme: boolean;
}
interface Matrix {
  cycles: { code: string; libelle: string; montant_n: string; significatif: boolean | null }[];
  assertions: { code: string; libelle: string }[];
  niveaux: string[];
  cellules: Cell[];
  crees?: number;
  mis_a_jour?: number;
}

const COLORS: Record<string, string> = { faible: "bg-emerald-100 text-emerald-900", moyen: "bg-amber-100 text-amber-900", eleve: "bg-red-100 text-red-900" };

/** Matrice des risques par cycle et par assertion, qui alimente le programme (REV-14). */
export default function RiskMatrixPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Matrix | null>(null);
  const [sel, setSel] = useState<{ cycle: string; assertion: string } | null>(null);
  const [form, setForm] = useState({ risque_inherent: "", risque_controle: "", risque_important: false, commentaire: "" });
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/risk-matrix`;
  useEffect(() => {
    api<Matrix>(url).then(setData).catch((e: Error) => setError(e.message));
  }, [url]);
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;

  const cell = (cycle: string, assertion: string) => data.cellules.find((c) => c.cycle === cycle && c.assertion === assertion);
  const open = (cycle: string, assertion: string) => {
    const c = cell(cycle, assertion);
    setSel({ cycle, assertion });
    setForm({ risque_inherent: c?.risque_inherent ?? "", risque_controle: c?.risque_controle ?? "", risque_important: c?.risque_important ?? false, commentaire: c?.commentaire ?? "" });
  };
  const run = async (fn: () => Promise<Matrix>) => {
    setError(null);
    setInfo(null);
    try {
      const m = await fn();
      setData(m);
      return m;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!sel) return;
    const body = { ...form, risque_inherent: form.risque_inherent || null, risque_controle: form.risque_controle || null, commentaire: form.commentaire || null };
    if (await run(() => put<Matrix>(`${url}/${sel.cycle}/${sel.assertion}`, body))) setSel(null);
  };
  const generate = async () => {
    const m = await run(() => post<Matrix>(`${url}/program`));
    if (m) setInfo(t("matrice.genere", { crees: m.crees, maj: m.mis_a_jour }));
  };
  const label = (lvl: string) => t(`matrice.niveaux.${lvl}`);
  const selCycle = data.cycles.find((c) => c.code === sel?.cycle);
  const selAssertion = data.assertions.find((a) => a.code === sel?.assertion);

  return (
    <section className="carte space-y-3" aria-labelledby="matrice-titre">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="matrice-titre" className="text-base font-semibold">{t("matrice.titre")}</h2>
        {file.peut_gerer && <button type="button" className="btn-primaire" onClick={() => void generate()}>{t("matrice.generer")}</button>}
      </div>
      <p className="text-sm text-slate-600">{t("matrice.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      {info && <Alert kind="succes">{info}</Alert>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-600">
            <tr>
              <th scope="col" className="py-1 pr-3 text-left">{t("matrice.cycle")}</th>
              {data.assertions.map((a) => <th key={a.code} scope="col" className="px-1 py-1">{a.libelle}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.cycles.map((c) => (
              <tr key={c.code}>
                <th scope="row" className="py-1 pr-3 text-left font-normal">
                  <span className="font-medium">{c.libelle}</span>
                  <span className={`block text-xs ${c.significatif ? "text-red-700" : "text-slate-600"}`}>
                    {formatNombre(Number(c.montant_n))}{c.significatif && ` · ${t("matrice.significatif")}`}
                  </span>
                </th>
                {data.assertions.map((a) => {
                  const v = cell(c.code, a.code);
                  const text = v?.risque ? label(v.risque) : "—";
                  return (
                    <td key={a.code} className="px-1 py-1 text-center">
                      <button type="button" disabled={!file.peut_travailler} onClick={() => open(c.code, a.code)}
                        aria-label={t("matrice.cellule", { cycle: c.libelle, assertion: a.libelle, niveau: text })}
                        className={`w-full rounded px-1 py-1 text-xs ${v?.risque ? COLORS[v.risque] : "bg-slate-50 text-slate-400"} ${sel?.cycle === c.code && sel.assertion === a.code ? "ring-2 ring-marque-600" : ""}`}>
                        {text}{v?.risque_important && " !"}{v?.dans_programme && " ✓"}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-600">{t("matrice.legende")}</p>
      {sel && (
        <form onSubmit={save} className="grid gap-2 rounded border border-slate-200 p-3 md:grid-cols-4">
          <p className="font-medium md:col-span-4">{selCycle?.libelle} – {selAssertion?.libelle}</p>
          {(["risque_inherent", "risque_controle"] as const).map((k) => (
            <div key={k}>
              <label htmlFor={`mx-${k}`} className="etiquette">{t(`matrice.${k}`)}</label>
              <select id={`mx-${k}`} className="champ" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })}>
                <option value="">—</option>
                {data.niveaux.map((n) => <option key={n} value={n}>{label(n)}</option>)}
              </select>
            </div>
          ))}
          <label className="flex items-end gap-2 text-sm"><input type="checkbox" checked={form.risque_important} onChange={(e) => setForm({ ...form, risque_important: e.target.checked })} />{t("matrice.important")}</label>
          <div className="md:col-span-4"><label htmlFor="mx-com" className="etiquette">{t("matrice.commentaire")}</label><textarea id="mx-com" rows={2} className="champ" value={form.commentaire} onChange={(e) => setForm({ ...form, commentaire: e.target.value })} /></div>
          <div className="flex gap-2"><button type="submit" className="btn-primaire">{t("commun.enregistrer")}</button><button type="button" className="btn-secondaire" onClick={() => setSel(null)}>{t("commun.annuler")}</button></div>
        </form>
      )}
    </section>
  );
}
