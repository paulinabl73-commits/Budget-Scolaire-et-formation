import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, patch, post } from "../api/client";
import type { Tickmark } from "../api/types";
import Alert from "../components/Alert";

export default function TickmarksPage() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Tickmark[]>([]);
  const [f, setF] = useState({ symbole: "", libelle: "", couleur: "#1f5fa8" });
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(null);
  const load = useCallback(async () => setRows(await api<Tickmark[]>("/tickmarks")), []);
  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
  }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setMessage(null);
    try {
      await action();
      setMessage({ kind: "succes", text: t("marques.enregistre") });
      await load();
      return true;
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
      return false;
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (await run(() => post("/tickmarks", { ...f, ordre: rows.length }))) setF({ symbole: "", libelle: "", couleur: "#1f5fa8" });
  };

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("marques.titre")}</h1>
        <p className="text-slate-600">{t("marques.intro")}</p>
      </header>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="carte">
        <table className="w-full text-left text-sm">
          <thead className="text-slate-600">
            <tr>
              <th scope="col" className="py-2">{t("marques.symbole")}</th>
              <th scope="col">{t("marques.libelle")}</th>
              <th scope="col">{t("marques.couleur")}</th>
              <th scope="col">{t("marques.actif")}</th>
              <th scope="col"><span className="sr-only">{t("utilisateurs.actions")}</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {rows.map((x) => (
              <tr key={x.id} className={x.actif ? "" : "text-slate-400"}>
                <td className="py-2 text-lg font-bold" style={{ color: x.couleur }}>{x.symbole}</td>
                <td>{x.libelle}</td>
                <td>
                  <input type="color" aria-label={`${t("marques.couleur")} ${x.symbole}`} defaultValue={x.couleur}
                    onBlur={(e) => e.target.value !== x.couleur && run(() => patch(`/tickmarks/${x.id}`, { couleur: e.target.value }))} />
                </td>
                <td>{x.actif ? t("commun.oui") : t("commun.non")}</td>
                <td>
                  <button type="button" className="text-sm text-marque-700 underline"
                    onClick={() => run(() => patch(`/tickmarks/${x.id}`, { actif: !x.actif }))}>
                    {x.actif ? t("marques.desactiver") : t("marques.activer")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form onSubmit={submit} className="carte flex flex-wrap items-end gap-3">
        <div className="w-24">
          <label htmlFor="tm-s" className="etiquette">{t("marques.symbole")}</label>
          <input id="tm-s" className="champ text-center text-lg" maxLength={4} required value={f.symbole}
            onChange={(e) => setF({ ...f, symbole: e.target.value })} />
        </div>
        <div className="min-w-64 flex-1">
          <label htmlFor="tm-l" className="etiquette">{t("marques.libelle")}</label>
          <input id="tm-l" className="champ" required value={f.libelle} onChange={(e) => setF({ ...f, libelle: e.target.value })} />
        </div>
        <div>
          <label htmlFor="tm-c" className="etiquette">{t("marques.couleur")}</label>
          <input id="tm-c" type="color" className="mt-1 h-10 w-16" value={f.couleur} onChange={(e) => setF({ ...f, couleur: e.target.value })} />
        </div>
        <button type="submit" className="btn-primaire">{t("marques.ajouter")}</button>
      </form>
    </div>
  );
}
