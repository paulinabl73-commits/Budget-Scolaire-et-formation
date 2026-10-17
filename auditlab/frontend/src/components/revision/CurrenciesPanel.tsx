import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { formatDate, formatDecimal } from "../../lib/format";
import { can, PERM } from "../../lib/permissions";
import Alert from "../Alert";

interface Currency { code: string; libelle: string; decimales: number }
interface Rate { id: string; devise_source: string; devise_cible: string; date: string; taux: string; source: string | null }

/** Devises et cours de conversion par date (REV-07). */
export default function CurrenciesPanel() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const admin = can(user?.permissions, PERM.FRAMEWORKS_MANAGE);
  const rateManager = admin || can(user?.permissions, PERM.REVISION_MANAGE);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [rates, setRates] = useState<Rate[]>([]);
  const [rate, setRate] = useState({ devise_source: "EUR", devise_cible: "XOF", date: "", taux: "", source: "" });
  const [cur, setCur] = useState({ code: "", libelle: "", decimales: "2" });
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setCurrencies(await api<Currency[]>("/currencies"));
    setRates(await api<Rate[]>("/exchange-rates"));
  }, []);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  const run = (fn: () => Promise<unknown>) => async (e?: FormEvent) => {
    e?.preventDefault();
    setError(null);
    try {
      await fn();
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const addRate = run(async () => {
    await post("/exchange-rates", { ...rate, taux: rate.taux.replace(/\s/g, "").replace(",", "."), source: rate.source || null });
    setRate({ ...rate, date: "", taux: "", source: "" });
  });
  const addCurrency = run(async () => {
    await post("/currencies", { ...cur, decimales: Number(cur.decimales) });
    setCur({ code: "", libelle: "", decimales: "2" });
  });
  const options = currencies.map((c) => <option key={c.code} value={c.code}>{c.code}</option>);

  return (
    <section className="carte space-y-3" aria-labelledby="devises-titre">
      <h2 id="devises-titre" className="text-lg font-semibold">{t("devises.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <p className="text-sm">
        {currencies.map((c) => `${c.code} – ${c.libelle} (${t("devises.decimales", { count: c.decimales })})`).join(" · ")}
      </p>
      {admin && (
        <form onSubmit={addCurrency} className="grid gap-2 md:grid-cols-4">
          <div><label htmlFor="cur-code" className="etiquette">{t("devises.code")}</label><input id="cur-code" className="champ" required pattern="[A-Z]{3}" maxLength={3} value={cur.code} onChange={(e) => setCur({ ...cur, code: e.target.value.toUpperCase() })} /></div>
          <div><label htmlFor="cur-lib" className="etiquette">{t("devises.libelle")}</label><input id="cur-lib" className="champ" required value={cur.libelle} onChange={(e) => setCur({ ...cur, libelle: e.target.value })} /></div>
          <div><label htmlFor="cur-dec" className="etiquette">{t("devises.nbDecimales")}</label><input id="cur-dec" type="number" min={0} max={4} className="champ" required value={cur.decimales} onChange={(e) => setCur({ ...cur, decimales: e.target.value })} /></div>
          <div className="flex items-end"><button type="submit" className="btn-secondaire">{t("devises.ajouterDevise")}</button></div>
        </form>
      )}
      <h3 className="font-semibold">{t("devises.cours")}</h3>
      {rateManager && (
        <form onSubmit={addRate} className="grid gap-2 md:grid-cols-6">
          <div><label htmlFor="rt-src" className="etiquette">{t("devises.source")}</label><select id="rt-src" className="champ" value={rate.devise_source} onChange={(e) => setRate({ ...rate, devise_source: e.target.value })}>{options}</select></div>
          <div><label htmlFor="rt-cib" className="etiquette">{t("devises.cible")}</label><select id="rt-cib" className="champ" value={rate.devise_cible} onChange={(e) => setRate({ ...rate, devise_cible: e.target.value })}>{options}</select></div>
          <div><label htmlFor="rt-date" className="etiquette">{t("devises.date")}</label><input id="rt-date" type="date" className="champ" required value={rate.date} onChange={(e) => setRate({ ...rate, date: e.target.value })} /></div>
          <div><label htmlFor="rt-taux" className="etiquette">{t("devises.taux", { source: rate.devise_source, cible: rate.devise_cible })}</label><input id="rt-taux" className="champ" inputMode="decimal" required value={rate.taux} onChange={(e) => setRate({ ...rate, taux: e.target.value })} /></div>
          <div><label htmlFor="rt-orig" className="etiquette">{t("devises.origine")}</label><input id="rt-orig" className="champ" placeholder={t("devises.originePlaceholder")} value={rate.source} onChange={(e) => setRate({ ...rate, source: e.target.value })} /></div>
          <div className="flex items-end"><button type="submit" className="btn-primaire">{t("devises.ajouterCours")}</button></div>
        </form>
      )}
      {rates.length === 0 ? <p className="text-sm text-slate-600">{t("devises.aucunCours")}</p> : (
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600"><tr>{["date", "paire", "taux", "origine", ""].map((k) => <th key={k} scope="col" className="py-1 pr-3">{k && t(`devises.col.${k}`)}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rates.map((r) => (
              <tr key={r.id}>
                <td className="py-1 pr-3">{formatDate(r.date)}</td>
                <td className="py-1 pr-3">{r.devise_source} → {r.devise_cible}</td>
                <td className="py-1 pr-3 font-mono">{formatDecimal(r.taux)}</td>
                <td className="py-1 pr-3">{r.source}</td>
                <td className="py-1 text-right">{rateManager && <button type="button" className="text-xs text-red-700 underline" onClick={() => void run(() => del(`/exchange-rates/${r.id}`))()}>{t("devises.supprimer")}</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
