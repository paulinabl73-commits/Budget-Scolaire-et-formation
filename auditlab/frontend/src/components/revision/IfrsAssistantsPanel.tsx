import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, post } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Assistant { code: string; norme: string; params: { nom: string; type: string; defaut: unknown }[] }
interface Result { norme: string; libelle: string; calcul: Record<string, unknown>; lignes: { compte: string; libelle: string; debit?: string; credit?: string }[] }

// Colonnes des paramètres de type liste (une ligne par élément, champs séparés par « ; »).
const LIST_FIELDS: Record<string, string[]> = {
  salaries: ["nom", "salaire_annuel", "anciennete", "age"],
  tranches: ["libelle", "montant", "taux_perte"],
  composants: ["libelle", "quote_part", "duree"],
  obligations: ["libelle", "prix_vente_spontane", "pct_execution"],
};

/** Assistants de calcul des retraitements IFRS (IFR-02). */
export default function IfrsAssistantsPanel({ file, onCreated }: { file: AuditFile; onCreated: () => void }) {
  const { t } = useTranslation();
  const [assistants, setAssistants] = useState<Assistant[]>([]);
  const [code, setCode] = useState("ifrs16");
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const defaults = (a: Assistant | undefined) =>
    Object.fromEntries((a?.params ?? []).map((p) => [p.nom, p.defaut === null || p.defaut === undefined ? "" : String(p.defaut)]));
  useEffect(() => {
    api<Assistant[]>("/ifrs/assistants")
      .then((list) => {
        setAssistants(list);
        setValues((v) => (Object.keys(v).length ? v : defaults(list.find((a) => a.code === "ifrs16"))));
      })
      .catch((e: Error) => setError(e.message));
  }, []);
  const current = assistants.find((a) => a.code === code);
  const choose = (next: string) => {
    setCode(next);
    setValues(defaults(assistants.find((a) => a.code === next)));
    setResult(null);
  };
  const parameters = () => {
    const out: Record<string, unknown> = {};
    for (const p of current?.params ?? []) {
      const v = values[p.nom] ?? "";
      if (!v) continue;
      out[p.nom] = p.type === "liste"
        ? v.split("\n").filter((l) => l.trim()).map((l) => Object.fromEntries(l.split(";").map((x, i) => [LIST_FIELDS[p.nom][i], x.trim()])))
        : p.type === "entier" ? Number(v) : v.replace(/\s/g, "").replace(",", ".");
      if (p.type === "texte" || p.type === "compte") out[p.nom] = v.trim();
    }
    return out;
  };
  const go = async (creer: boolean) => {
    setError(null);
    setInfo(null);
    try {
      const r = await post<Result & { retraitement?: { numero: number } }>(`/audit-files/${file.id}/ifrs/assistants/${code}`, { parametres: parameters(), creer });
      setResult(r);
      if (r.retraitement) {
        setInfo(t("ifrsAssistants.cree", { numero: r.retraitement.numero }));
        onCreated();
      }
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const show = (v: unknown) => (typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v) ? formatNombre(Number(v)) : String(v));

  return (
    <section className="carte space-y-3" aria-labelledby="ifa-titre">
      <h2 id="ifa-titre" className="text-base font-semibold">{t("ifrsAssistants.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {info && <Alert kind="succes">{info}</Alert>}
      <div><label htmlFor="ifa-code" className="etiquette">{t("ifrsAssistants.assistant")}</label>
        <select id="ifa-code" className="champ max-w-md" value={code} onChange={(e) => choose(e.target.value)}>{assistants.map((a) => <option key={a.code} value={a.code}>{t(`ifrsAssistants.noms.${a.code}`)}</option>)}</select></div>
      <div className="grid gap-2 md:grid-cols-3">
        {current?.params.map((p) => (
          <div key={p.nom} className={p.type === "liste" ? "md:col-span-3" : ""}>
            <label htmlFor={`ifa-${p.nom}`} className="etiquette">{t(`ifrsAssistants.params.${p.nom}`, { defaultValue: p.nom })}</label>
            {p.type === "liste" ? (
              <>
                <textarea id={`ifa-${p.nom}`} rows={3} className="champ font-mono" value={values[p.nom] ?? ""} onChange={(e) => setValues({ ...values, [p.nom]: e.target.value })} />
                <p className="text-xs text-slate-500">{t("ifrsAssistants.format", { colonnes: LIST_FIELDS[p.nom]?.map((c) => t(`ifrsAssistants.params.${c}`, { defaultValue: c })).join(" ; ") })}</p>
              </>
            ) : (
              <input id={`ifa-${p.nom}`} className="champ" inputMode={p.type === "texte" ? undefined : "decimal"} value={values[p.nom] ?? ""} onChange={(e) => setValues({ ...values, [p.nom]: e.target.value })} />
            )}
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <button type="button" className="btn-secondaire" onClick={() => void go(false)}>{t("ifrsAssistants.calculer")}</button>
        {file.peut_travailler && <button type="button" className="btn-primaire" onClick={() => void go(true)}>{t("ifrsAssistants.creer")}</button>}
      </div>
      {result && (
        <div className="space-y-2 text-sm">
          <dl className="grid gap-x-4 md:grid-cols-[max-content_1fr]">
            {Object.entries(result.calcul).filter(([, v]) => !Array.isArray(v)).map(([k, v]) => (
              <div key={k} className="contents"><dt className="text-slate-600">{t(`ifrsAssistants.resultats.${k}`, { defaultValue: k })}</dt><dd className="font-mono">{show(v)}</dd></div>
            ))}
          </dl>
          <table className="text-xs"><caption className="text-left font-medium">{t("ifrsAssistants.ecriture")}</caption>
            <tbody>{result.lignes.map((l, i) => <tr key={i}><td className="pr-3 font-mono">{l.compte}</td><td className="pr-3">{l.libelle}</td><td className="pr-3 text-right font-mono">{l.debit ? formatNombre(Number(l.debit)) : ""}</td><td className="text-right font-mono">{l.credit ? formatNombre(Number(l.credit)) : ""}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}
