import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, post } from "../../api/client";
import type { Dataset } from "../../api/types";
import Alert from "../Alert";

interface Macro {
  id: string;
  nom: string;
  description: string | null;
  entrees: { nom: string; colonnes: { nom: string; type: string }[] }[];
  etapes: { nom: string; kind: string; operation?: string }[];
}

/** Exécution d'une macro sur des tables de la mission (DAT-25). */
export default function MacroPanel({ tables, onDone }: { tables: Dataset[]; onDone: (text: string, ok: boolean) => void }) {
  const { t } = useTranslation();
  const [macros, setMacros] = useState<Macro[]>([]);
  const [id, setId] = useState("");
  const [inputs, setInputs] = useState<string[]>([]);
  const [suffixe, setSuffixe] = useState("");
  useEffect(() => {
    api<Macro[]>("/macros").then(setMacros).catch(() => setMacros([]));
  }, []);
  const macro = macros.find((m) => m.id === id);
  const ready = tables.filter((d) => d.statut === "pret");

  const run = async () => {
    try {
      const created = await post<Dataset[]>(`/macros/${id}/run`, { entrees: inputs, suffixe });
      onDone(t("macros.lancee", { n: created.length }), true);
    } catch (e) {
      onDone((e as Error).message, false);
    }
  };

  if (macros.length === 0) return null;
  return (
    <section className="carte space-y-2" aria-labelledby="macro-titre">
      <h2 id="macro-titre" className="text-base font-semibold">{t("macros.titre")}</h2>
      <div className="grid gap-2 md:grid-cols-3">
        <div>
          <label htmlFor="macro-choix" className="etiquette">{t("macros.macro")}</label>
          <select id="macro-choix" className="champ" value={id}
            onChange={(e) => { setId(e.target.value); setInputs(macros.find((m) => m.id === e.target.value)?.entrees.map(() => "") ?? []); }}>
            <option value="">—</option>
            {macros.map((m) => <option key={m.id} value={m.id}>{m.nom}</option>)}
          </select>
        </div>
        {macro?.entrees.map((entree, i) => (
          <div key={i}>
            <label htmlFor={`macro-in-${i}`} className="etiquette">{t("macros.entree", { nom: entree.nom })}</label>
            <select id={`macro-in-${i}`} className="champ" value={inputs[i] ?? ""}
              onChange={(e) => setInputs(inputs.map((x, j) => (j === i ? e.target.value : x)))}>
              <option value="">—</option>
              {ready.map((d) => <option key={d.id} value={d.id}>{d.nom}</option>)}
            </select>
          </div>
        ))}
        {macro && (
          <div>
            <label htmlFor="macro-suffixe" className="etiquette">{t("macros.suffixe")}</label>
            <input id="macro-suffixe" className="champ" maxLength={60} value={suffixe} onChange={(e) => setSuffixe(e.target.value)} />
          </div>
        )}
      </div>
      {macro && (
        <>
          <p className="text-sm text-slate-600">
            {macro.description && `${macro.description} — `}
            {t("macros.etapes")} : {macro.etapes.map((s) => (s.kind === "vue" ? t("donnees.kinds.vue") : t(`analyses.${s.operation}.titre`))).join(" → ")}
          </p>
          <button type="button" className="btn-primaire" disabled={inputs.some((x) => !x)} onClick={run}>{t("macros.executer")}</button>
        </>
      )}
    </section>
  );
}

/** Enregistrement de l'historique d'une table en macro (DAT-25). */
export function SaveMacro({ ds }: { ds: Dataset }) {
  const { t } = useTranslation();
  const [nom, setNom] = useState("");
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const save = async () => {
    try {
      await post(`/datasets/${ds.id}/macro`, { nom });
      setResult({ ok: true, text: t("macros.enregistree", { nom }) });
      setNom("");
    } catch (e) {
      setResult({ ok: false, text: (e as Error).message });
    }
  };
  return (
    <div className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-2">
      <div>
        <label htmlFor="macro-nom" className="etiquette">{t("macros.nomMacro")}</label>
        <input id="macro-nom" className="champ mt-0" maxLength={200} value={nom} onChange={(e) => setNom(e.target.value)} />
      </div>
      <button type="button" className="btn-secondaire" disabled={!nom.trim()} onClick={save}>{t("macros.enregistrer")}</button>
      {result && <Alert kind={result.ok ? "succes" : "erreur"}>{result.text}</Alert>}
    </div>
  );
}
