import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download, patch, tokenStore } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { can, PERM } from "../../lib/permissions";
import Alert from "../Alert";
import type { DsfModelSummary } from "./DsfPanel";

/** Modèles de liasse fiscale et statistique par pays (REV-25). */
export default function DsfModelsPanel() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const manager = can(user?.permissions, PERM.FRAMEWORKS_MANAGE);
  const [models, setModels] = useState<DsfModelSummary[]>([]);
  const [form, setForm] = useState({ pays: "", nom: "", version: "" });
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback(async () => setModels(await api<DsfModelSummary[]>("/dsf-models")), []);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const send = async () => {
    setError(null);
    const f = input.current?.files?.[0];
    if (!f) return;
    const body = new FormData();
    Object.entries(form).forEach(([k, v]) => body.append(k, v));
    body.append("file", f);
    const headers = new Headers();
    const token = tokenStore.get();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const resp = await fetch("/api/dsf-models/import", { method: "POST", body, headers });
    const json = await resp.json();
    if (!resp.ok) setError(typeof json.detail === "string" ? json.detail : resp.statusText);
    else await load();
  };
  return (
    <section className="carte space-y-3" aria-labelledby="dsfm-titre">
      <h2 id="dsfm-titre" className="text-lg font-semibold">{t("dsf.modeles")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <ul className="text-sm">
        {models.map((m) => (
          <li key={m.id} className={`flex flex-wrap items-center gap-2 ${m.actif ? "" : "text-slate-400"}`}>
            <strong>{m.pays}</strong> {m.nom} ({m.version}) · {m.feuilles.map((f) => f.nom).join(", ")}
            <button type="button" className="text-xs underline" onClick={() => void download(`/dsf-models/${m.id}/template`, undefined, "modele_dsf.xlsx")}>{t("dsf.gabarit")}</button>
            {manager && <button type="button" className="text-xs underline" onClick={() => void patch(`/dsf-models/${m.id}?actif=${!m.actif}`, {}).then(load)}>{m.actif ? t("programmes.desactiver") : t("programmes.reactiver")}</button>}
          </li>
        ))}
      </ul>
      {manager && (
        <div className="grid gap-2 md:grid-cols-5">
          <div><label htmlFor="dsfm-pays" className="etiquette">{t("dsf.pays")}</label><input id="dsfm-pays" className="champ" maxLength={10} value={form.pays} onChange={(e) => setForm({ ...form, pays: e.target.value })} /></div>
          <div><label htmlFor="dsfm-nom" className="etiquette">{t("dsf.nom")}</label><input id="dsfm-nom" className="champ" value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} /></div>
          <div><label htmlFor="dsfm-version" className="etiquette">{t("dsf.version")}</label><input id="dsfm-version" className="champ" value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} /></div>
          <div><label htmlFor="dsfm-fichier" className="etiquette">{t("dsf.fichier")}</label><input id="dsfm-fichier" ref={input} type="file" accept=".xlsx" className="text-sm" /></div>
          <div className="flex items-end"><button type="button" className="btn-secondaire" onClick={() => void send()}>{t("dsf.importer")}</button></div>
        </div>
      )}
    </section>
  );
}
