import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, post } from "../api/client";
import { FORMES, REGIMES, TAILLES } from "../api/portfolio";
import type { PortfolioClient, PortfolioStaff } from "../api/portfolio";
import type { FrameworkSummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import CalendarRulesPanel from "../components/portfolio/CalendarRulesPanel";
import FiscalParametersPanel from "../components/portfolio/FiscalParametersPanel";
import PortfolioDashboard from "../components/portfolio/PortfolioDashboard";
import { can, PERM } from "../lib/permissions";

/** Portefeuille de dossiers clients du cabinet (RCO-01). */
export default function PortfolioPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [clients, setClients] = useState<PortfolioClient[] | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = () => api<PortfolioClient[]>("/clients").then(setClients).catch((e: Error) => setError(e.message));
  useEffect(() => {
    void load();
  }, []);
  const manager = can(user?.permissions, PERM.PORTFOLIO_MANAGE);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t("portefeuille.titre")}</h1>
        {manager && <button type="button" className="btn-primaire" onClick={() => setShowForm((v) => !v)}>{t("portefeuille.nouveau")}</button>}
      </div>
      {error && <Alert kind="erreur">{error}</Alert>}
      <PortfolioDashboard />
      {showForm && <ClientForm onCreated={() => { setShowForm(false); void load(); }} />}
      {clients && (clients.length === 0 ? <p className="text-sm text-slate-600">{t("portefeuille.aucun")}</p> : (
        <div className="carte overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-600">
              <tr>
                {["raison", "forme", "regime", "referentiel", "cloture", "collaborateur", "superviseur", "clotures"].map((k) => (
                  <th key={k} scope="col" className="px-4 py-2">{t(`portefeuille.${k}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {clients.map((c) => (
                <tr key={c.id}>
                  <th scope="row" className="px-4 py-2 font-medium">
                    <Link to={`/portefeuille/${c.id}`} className="text-marque-700 underline">{c.raison_sociale}</Link>
                    {!c.actif && <span className="ml-1 text-xs text-slate-500">({t("portefeuille.inactif")})</span>}
                  </th>
                  <td className="px-4">{t(`portefeuille.formes.${c.forme_juridique}`)}</td>
                  <td className="px-4">{t(`portefeuille.regimes.${c.regime_fiscal}`)}</td>
                  <td className="px-4">{c.referentiel}</td>
                  <td className="px-4">{c.date_cloture}</td>
                  <td className="px-4">{c.collaborateur_nom ?? "—"}</td>
                  <td className="px-4">{c.superviseur_nom ?? c.expert_nom}</td>
                  <td className="px-4">{c.clotures.map((x) => `${x.exercice} · ${t(`portefeuille.etapes.${x.etape}`)}`).join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {manager && <CalendarRulesPanel />}
      {manager && <FiscalParametersPanel />}
    </div>
  );
}

function ClientForm({ onCreated }: { onCreated: () => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [staff, setStaff] = useState<PortfolioStaff | null>(null);
  const [frameworks, setFrameworks] = useState<FrameworkSummary[]>([]);
  const [f, setF] = useState<Record<string, string>>({
    raison_sociale: "", forme_juridique: "SARL", regime_fiscal: "reel_normal", framework_id: "", pays: "", devise: "XOF",
    jour_cloture: "31", mois_cloture: "12", taille: "pme", identifiant_fiscal: "", rccm: "",
    expert_id: "", collaborateur_id: "", superviseur_id: "", contact_id: "", budget_jours: "5",
  });
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<PortfolioStaff>("/portfolio/staff").then(setStaff).catch(() => setStaff(null));
    api<FrameworkSummary[]>("/frameworks").then((all) => setFrameworks(all.filter((x) => x.actif && ["SYSCOHADA", "CIPRES"].includes(x.code)))).catch(() => setFrameworks([]));
  }, []);
  const set = (k: string, v: string) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const body: Record<string, unknown> = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v]));
    for (const k of ["jour_cloture", "mois_cloture", "budget_jours"]) body[k] = Number(f[k]);
    try {
      await post("/clients", body);
      onCreated();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const field = (k: string, type = "text", required = false) => (
    <div key={k}>
      <label htmlFor={`cl-${k}`} className="etiquette">{t(`portefeuille.${LABELS[k] ?? k}`)}</label>
      <input id={`cl-${k}`} type={type} className="champ" required={required} value={f[k]} onChange={(e) => set(k, e.target.value)} />
    </div>
  );
  const choice = (k: string, options: readonly string[], prefix: string) => (
    <div key={k}>
      <label htmlFor={`cl-${k}`} className="etiquette">{t(`portefeuille.${LABELS[k] ?? k}`)}</label>
      <select id={`cl-${k}`} className="champ" value={f[k]} onChange={(e) => set(k, e.target.value)}>
        {options.map((o) => <option key={o} value={o}>{t(`portefeuille.${prefix}.${o}`)}</option>)}
      </select>
    </div>
  );
  const person = (k: string, list: { id: string; nom: string }[] | undefined, required = false) => (
    <div key={k}>
      <label htmlFor={`cl-${k}`} className="etiquette">{t(`portefeuille.${LABELS[k]}`)}</label>
      <select id={`cl-${k}`} className="champ" required={required} value={f[k]} onChange={(e) => set(k, e.target.value)}>
        <option value="">{t("portefeuille.aucunChoix")}</option>
        {(list ?? []).map((u) => <option key={u.id} value={u.id}>{u.nom}</option>)}
      </select>
    </div>
  );
  return (
    <form onSubmit={submit} className="carte grid gap-3 md:grid-cols-3" aria-label={t("portefeuille.nouveau")}>
      {error && <div className="md:col-span-3"><Alert kind="erreur">{error}</Alert></div>}
      {field("raison_sociale", "text", true)}
      {choice("forme_juridique", FORMES, "formes")}
      {choice("regime_fiscal", REGIMES, "regimes")}
      <div>
        <label htmlFor="cl-framework_id" className="etiquette">{t("portefeuille.referentiel")}</label>
        <select id="cl-framework_id" className="champ" required value={f.framework_id} onChange={(e) => set("framework_id", e.target.value)}>
          <option value="">{t("portefeuille.aucunChoix")}</option>
          {frameworks.map((x) => <option key={x.id} value={x.id}>{x.code} {x.version} ({x.pays})</option>)}
        </select>
      </div>
      {field("pays", "text", true)}
      {field("devise", "text", true)}
      {field("jour_cloture", "number", true)}
      {field("mois_cloture", "number", true)}
      {choice("taille", TAILLES, "tailles")}
      {field("identifiant_fiscal")}
      {field("rccm")}
      {field("budget_jours", "number", true)}
      {user?.role !== "expert_comptable" && person("expert_id", staff?.experts, true)}
      {person("collaborateur_id", staff?.collaborateurs)}
      {person("superviseur_id", staff?.superviseurs)}
      {person("contact_id", staff?.contacts)}
      <div className="md:col-span-3"><button type="submit" className="btn-primaire">{t("portefeuille.creer")}</button></div>
    </form>
  );
}

const LABELS: Record<string, string> = {
  raison_sociale: "raison", forme_juridique: "forme", regime_fiscal: "regime", jour_cloture: "jour", mois_cloture: "mois",
  identifiant_fiscal: "nif", budget_jours: "budget", expert_id: "expert", collaborateur_id: "collaborateur",
  superviseur_id: "superviseur", contact_id: "contact",
};
