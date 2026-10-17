import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, put } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal, formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Materiality {
  bases: { code: string; libelle: string; pct_min: string | null; pct_max: string | null; montant: string | null }[];
  etats_indisponibles: string | null;
  defauts: { pct_planification: string; pct_insignifiant: string };
  seuil: Record<string, string | null>;
  avertissements?: string[];
}

const toNumber = (v: string) => v.replace(/\s/g, "").replace(",", ".");

/** Seuil de signification et seuils dérivés (REV-11). */
export default function MaterialityPanel({ file, onChange }: { file: AuditFile; onChange: () => void }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Materiality | null>(null);
  const [form, setForm] = useState({ base_seuil: "", pct_seuil: "", montant_base: "", pct_planification: "", pct_insignifiant: "", seuil_variation_pct: "", justification: "" });
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const fill = (m: Materiality) => {
    setData(m);
    const s = m.seuil;
    setForm({
      base_seuil: s.base_seuil ?? m.bases[0]?.code ?? "",
      pct_seuil: formatDecimal(s.pct_seuil),
      montant_base: "",
      pct_planification: formatDecimal(s.pct_planification ?? m.defauts.pct_planification),
      pct_insignifiant: formatDecimal(s.pct_insignifiant ?? m.defauts.pct_insignifiant),
      seuil_variation_pct: formatDecimal(s.seuil_variation_pct),
      justification: s.justification_seuil ?? "",
    });
  };
  useEffect(() => {
    api<Materiality>(`/audit-files/${file.id}/materiality`).then(fill).catch((e: Error) => setError(e.message));
  }, [file.id]);
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;

  const base = data.bases.find((b) => b.code === form.base_seuil);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const body = {
        base_seuil: form.base_seuil,
        pct_seuil: toNumber(form.pct_seuil),
        montant_base: form.montant_base ? toNumber(form.montant_base) : null,
        pct_planification: toNumber(form.pct_planification),
        pct_insignifiant: toNumber(form.pct_insignifiant),
        seuil_variation_pct: form.seuil_variation_pct ? toNumber(form.seuil_variation_pct) : null,
        justification: form.justification,
      };
      const m = await put<Materiality>(`/audit-files/${file.id}/materiality`, body);
      fill(m);
      setWarnings(m.avertissements ?? []);
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const s = data.seuil;
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  return (
    <section className="carte space-y-3" aria-labelledby="seuil-titre">
      <h2 id="seuil-titre" className="text-base font-semibold">{t("seuil.titre")}</h2>
      {s.seuil_signification ? (
        <dl className="grid gap-2 text-sm md:grid-cols-3">
          {[["seuil_signification", "pct_seuil"], ["seuil_planification", "pct_planification"], ["seuil_insignifiant", "pct_insignifiant"]].map(([k, pct]) => (
            <div key={k} className="rounded border border-slate-200 p-2">
              <dt className="text-xs text-slate-600">{t(`seuil.${k}`)}</dt>
              <dd className="text-lg font-semibold">{formatNombre(Number(s[k]))} {file.devise}</dd>
              <dd className="text-xs text-slate-600">{formatDecimal(s[pct])} % {k === "seuil_signification" ? t("seuil.de", { base: data.bases.find((b) => b.code === s.base_seuil)?.libelle ?? s.base_seuil, montant: formatNombre(Number(s.montant_base)) }) : t("seuil.duSeuil")}</dd>
            </div>
          ))}
        </dl>
      ) : <p className="text-sm text-slate-600">{t("seuil.nonFixe")}</p>}
      {data.etats_indisponibles && <p className="text-sm text-amber-800">{t("seuil.basesIndisponibles", { raison: data.etats_indisponibles })}</p>}
      {error && <Alert kind="erreur">{error}</Alert>}
      {warnings.map((w) => <Alert key={w} kind="info">{w}</Alert>)}
      {file.peut_gerer && (
        <form onSubmit={submit} className="grid gap-2 md:grid-cols-4">
          <div className="md:col-span-2">
            <label htmlFor="ss-base" className="etiquette">{t("seuil.base")}</label>
            <select id="ss-base" className="champ" value={form.base_seuil} onChange={set("base_seuil")}>
              {data.bases.map((b) => <option key={b.code} value={b.code}>{b.libelle}{b.montant ? ` – ${formatNombre(Number(b.montant))}` : ""}</option>)}
            </select>
            {base?.pct_min && <p className="text-xs text-slate-600">{t("seuil.fourchette", { min: formatDecimal(base.pct_min), max: formatDecimal(base.pct_max) })}</p>}
          </div>
          <div><label htmlFor="ss-pct" className="etiquette">{t("seuil.pct")}</label><input id="ss-pct" className="champ" inputMode="decimal" required value={form.pct_seuil} onChange={set("pct_seuil")} /></div>
          <div><label htmlFor="ss-mt" className="etiquette">{t("seuil.montantSaisi")}</label><input id="ss-mt" className="champ" inputMode="decimal" placeholder={base?.montant ? formatNombre(Number(base.montant)) : ""} value={form.montant_base} onChange={set("montant_base")} /></div>
          <div><label htmlFor="ss-plan" className="etiquette">{t("seuil.pctPlanification")}</label><input id="ss-plan" className="champ" inputMode="decimal" required value={form.pct_planification} onChange={set("pct_planification")} /></div>
          <div><label htmlFor="ss-ins" className="etiquette">{t("seuil.pctInsignifiant")}</label><input id="ss-ins" className="champ" inputMode="decimal" required value={form.pct_insignifiant} onChange={set("pct_insignifiant")} /></div>
          <div><label htmlFor="ss-var" className="etiquette">{t("seuil.pctVariation")}</label><input id="ss-var" className="champ" inputMode="decimal" value={form.seuil_variation_pct} onChange={set("seuil_variation_pct")} /></div>
          <div className="md:col-span-4"><label htmlFor="ss-just" className="etiquette">{t("seuil.justification")}</label><textarea id="ss-just" className="champ" rows={2} required minLength={10} value={form.justification} onChange={set("justification")} /></div>
          <div><button type="submit" className="btn-primaire">{t("seuil.fixer")}</button></div>
        </form>
      )}
    </section>
  );
}
