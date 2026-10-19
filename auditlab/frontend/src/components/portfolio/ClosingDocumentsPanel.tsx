import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, del, download, post, put } from "../../api/client";
import { formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

interface Recommendation {
  constat: string;
  recommandation: string;
}
interface Params {
  lieu: string | null;
  honoraires: string | null;
  observations: string | null;
  recommandations: Recommendation[];
}
interface Docs {
  parametres: Params;
  modeles: { code: string; nom: string }[];
  signature: {
    le: string;
    par: string;
    empreinte: string;
    conforme: boolean;
  } | null;
  peut_signer: boolean;
  visa_expert: boolean;
}

/** Documents de la clôture (RCO-25) : paramètres, téléchargements et attestation signée. */
export default function ClosingDocumentsPanel({
  closingId,
  exercice,
}: {
  closingId: string;
  exercice: number;
}) {
  const { t } = useTranslation();
  const [data, setData] = useState<Docs | null>(null);
  const [form, setForm] = useState<Params | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const url = `/closings/${closingId}/documents`;
  const apply = (d: Docs) => {
    setData(d);
    setForm(d.parametres);
  };
  const load = useCallback(() => api<Docs>(url).then(apply), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const run = async (action: () => Promise<Docs>, done?: string) => {
    setError(null);
    setInfo(null);
    try {
      apply(await action());
      if (done) setInfo(done);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  if (!data || !form)
    return error ? <Alert kind="erreur">{error}</Alert> : null;
  const set = (patch: Partial<Params>) => setForm({ ...form, ...patch });
  const setReco = (i: number, patch: Partial<Recommendation>) =>
    set({
      recommandations: form.recommandations.map((r, j) =>
        j === i ? { ...r, ...patch } : r,
      ),
    });
  const get = (code: string, fmt: string) =>
    void download(
      `${url}/${code}?format=${fmt}`,
      undefined,
      `${code}_${exercice}.${fmt}`,
    ).catch((e: Error) => setError(e.message));
  const sig = data.signature;
  return (
    <section className="carte space-y-3" aria-labelledby={`docs-${closingId}`}>
      <h2 id={`docs-${closingId}`} className="text-base font-semibold">
        {t("documentsCloture.titre")}
      </h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {info && <Alert kind="succes">{info}</Alert>}
      <form
        className="grid gap-2 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run(
            () => put<Docs>(url, form),
            t("documentsCloture.enregistre"),
          );
        }}
      >
        <label className="etiquette">
          {t("documentsCloture.lieu")}
          <input
            className="champ"
            value={form.lieu ?? ""}
            onChange={(e) => set({ lieu: e.target.value })}
          />
        </label>
        <label className="etiquette">
          {t("documentsCloture.honoraires")}
          <input
            className="champ"
            value={form.honoraires ?? ""}
            onChange={(e) => set({ honoraires: e.target.value })}
          />
        </label>
        <label className="etiquette md:col-span-2">
          {t("documentsCloture.observations")}
          <textarea
            className="champ"
            rows={2}
            value={form.observations ?? ""}
            onChange={(e) => set({ observations: e.target.value })}
          />
        </label>
        <fieldset className="space-y-2 md:col-span-2">
          <legend className="etiquette">
            {t("documentsCloture.recommandations")}
          </legend>
          {form.recommandations.map((r, i) => (
            <div key={i} className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
              <input
                className="champ"
                aria-label={t("documentsCloture.constat")}
                placeholder={t("documentsCloture.constat")}
                value={r.constat}
                onChange={(e) => setReco(i, { constat: e.target.value })}
              />
              <input
                className="champ"
                aria-label={t("documentsCloture.recommandation")}
                placeholder={t("documentsCloture.recommandation")}
                value={r.recommandation}
                onChange={(e) => setReco(i, { recommandation: e.target.value })}
              />
              <button
                type="button"
                className="underline"
                onClick={() =>
                  set({
                    recommandations: form.recommandations.filter(
                      (_, j) => j !== i,
                    ),
                  })
                }
              >
                {t("documentsCloture.retirer")}
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn-secondaire"
            onClick={() =>
              set({
                recommandations: [
                  ...form.recommandations,
                  { constat: "", recommandation: "" },
                ],
              })
            }
          >
            {t("documentsCloture.ajouter")}
          </button>
        </fieldset>
        <div className="md:col-span-2">
          <button type="submit" className="btn-primaire">
            {t("documentsCloture.enregistrer")}
          </button>
        </div>
      </form>
      <ul className="space-y-1 text-sm">
        {data.modeles.map((m) => (
          <li key={m.code} className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{m.nom}</span>
            <button
              type="button"
              className="underline"
              onClick={() => get(m.code, "pdf")}
            >
              PDF
            </button>
            <button
              type="button"
              className="underline"
              onClick={() => get(m.code, "docx")}
            >
              Word
            </button>
          </li>
        ))}
      </ul>
      <div className="space-y-1 text-sm">
        <p className="font-medium">
          {sig
            ? t("documentsCloture.signee", {
                par: sig.par,
                le: formatDateHeure(sig.le),
              })
            : t("documentsCloture.nonSignee")}
        </p>
        {sig && !sig.conforme && (
          <Alert kind="erreur">{t("documentsCloture.nonConforme")}</Alert>
        )}
        {!sig && !data.visa_expert && (
          <p className="text-slate-700">{t("documentsCloture.visaAttendu")}</p>
        )}
        {data.peut_signer && !sig && (
          <button
            type="button"
            className="btn-primaire"
            disabled={!data.visa_expert}
            onClick={() =>
              void run(() => post<Docs>(`${url}/presentation/sign`))
            }
          >
            {t("documentsCloture.signer")}
          </button>
        )}
        {data.peut_signer && sig && (
          <button
            type="button"
            className="underline"
            onClick={() =>
              void run(() =>
                del(`${url}/presentation/sign`).then(() => api<Docs>(url)),
              )
            }
          >
            {t("documentsCloture.annuler")}
          </button>
        )}
      </div>
    </section>
  );
}
