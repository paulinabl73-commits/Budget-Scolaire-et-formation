import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post, put } from "../api/client";
import Alert from "../components/Alert";

interface Section {
  code: string;
  titre: string;
  actif: boolean;
}
interface Template {
  id: string;
  nom: string;
  par_defaut: boolean;
  page_garde: {
    organisation: string;
    titre: string;
    sous_titre: string;
    mention: string;
  };
  sections: Section[];
  ordre_constats: string;
  pied_de_page: string | null;
  actif: boolean;
  logo: boolean;
}
type Draft = Omit<Template, "id" | "par_defaut" | "logo">;

const ORDRES = ["criticite_decroissante", "criticite_croissante", "reference"];

/** Modèles de rapport de mission (REP-01) : page de garde, logo, sections, ordre des constats. */
export default function ReportTemplatesPage() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Template[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [form, setForm] = useState<Draft | null>(null);
  const [message, setMessage] = useState<{
    kind: "erreur" | "succes";
    text: string;
  } | null>(null);
  const load = useCallback(
    () =>
      api<Template[]>("/mission-report-templates").then((list) => {
        setRows(list);
        return list;
      }),
    [],
  );
  const select = (tpl: Template) => {
    setCurrent(tpl.id);
    setForm({
      nom: tpl.nom,
      page_garde: tpl.page_garde,
      sections: tpl.sections,
      ordre_constats: tpl.ordre_constats,
      pied_de_page: tpl.pied_de_page,
      actif: tpl.actif,
    });
  };
  useEffect(() => {
    load().then(
      (list) => list[0] && select(list[0]),
      (e: Error) => setMessage({ kind: "erreur", text: e.message }),
    );
  }, [load]);
  const run = async (action: () => Promise<unknown>, done: string) => {
    setMessage(null);
    try {
      await action();
      await load();
      setMessage({ kind: "succes", text: done });
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
    }
  };
  const tpl = rows.find((r) => r.id === current);
  const move = (i: number, d: number) => {
    if (!form) return;
    const s = [...form.sections];
    [s[i], s[i + d]] = [s[i + d], s[i]];
    setForm({ ...form, sections: s });
  };
  const uploadLogo = (file: File) =>
    run(() => {
      const data = new FormData();
      data.append("file", file);
      return api(`/mission-report-templates/${current}/logo`, {
        method: "PUT",
        body: data,
      });
    }, t("modelesRapport.logoCharge"));
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("modelesRapport.titre")}</h1>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="flex flex-wrap gap-2">
        {rows.map((r) => (
          <button
            key={r.id}
            type="button"
            aria-pressed={r.id === current}
            className={r.id === current ? "btn-primaire" : "btn-secondaire"}
            onClick={() => select(r)}
          >
            {r.nom}
            {r.par_defaut && ` (${t("modelesRapport.defaut")})`}
          </button>
        ))}
        {form && (
          <button
            type="button"
            className="underline"
            onClick={() =>
              void run(async () => {
                const n = await post<Template>("/mission-report-templates", {
                  ...form,
                  nom: `${form.nom} (copie)`,
                });
                setCurrent(n.id);
              }, t("modelesRapport.copie"))
            }
          >
            {t("modelesRapport.dupliquer")}
          </button>
        )}
      </div>
      {form && tpl && (
        <form
          className="carte space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run(
              () => put(`/mission-report-templates/${tpl.id}`, form),
              t("modelesRapport.enregistre"),
            );
          }}
        >
          <label className="etiquette">
            {t("modelesRapport.nom")}
            <input
              className="champ"
              required
              minLength={3}
              value={form.nom}
              onChange={(e) => setForm({ ...form, nom: e.target.value })}
            />
          </label>
          <fieldset className="grid gap-2 md:grid-cols-2">
            <legend className="font-semibold">
              {t("modelesRapport.garde")}
            </legend>
            {(["organisation", "titre", "sous_titre", "mention"] as const).map(
              (k) => (
                <label key={k} className="etiquette">
                  {t(`modelesRapport.champs.${k}`)}
                  <input
                    className="champ"
                    required={k === "titre"}
                    value={form.page_garde[k]}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        page_garde: { ...form.page_garde, [k]: e.target.value },
                      })
                    }
                  />
                </label>
              ),
            )}
            <p className="text-xs text-slate-600 md:col-span-2">
              {t("modelesRapport.variables")}
            </p>
          </fieldset>
          <fieldset className="space-y-1">
            <legend className="font-semibold">
              {t("modelesRapport.sections")}
            </legend>
            {form.sections.map((s, i) => (
              <div key={s.code} className="flex flex-wrap items-center gap-2">
                <input
                  type="checkbox"
                  aria-label={t("modelesRapport.inclure", { section: s.titre })}
                  checked={s.actif}
                  disabled={s.code === "constats"}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      sections: form.sections.map((x) =>
                        x.code === s.code
                          ? { ...x, actif: e.target.checked }
                          : x,
                      ),
                    })
                  }
                />
                <input
                  className="champ max-w-md"
                  aria-label={t("modelesRapport.titreSection", {
                    code: t(`modelesRapport.codes.${s.code}`),
                  })}
                  value={s.titre}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      sections: form.sections.map((x) =>
                        x.code === s.code ? { ...x, titre: e.target.value } : x,
                      ),
                    })
                  }
                />
                <span className="text-xs text-slate-600">
                  {t(`modelesRapport.codes.${s.code}`)}
                </span>
                <button
                  type="button"
                  className="underline"
                  disabled={i === 0}
                  onClick={() => move(i, -1)}
                  aria-label={t("modelesRapport.monter", { section: s.titre })}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="underline"
                  disabled={i === form.sections.length - 1}
                  onClick={() => move(i, 1)}
                  aria-label={t("modelesRapport.descendre", {
                    section: s.titre,
                  })}
                >
                  ↓
                </button>
              </div>
            ))}
          </fieldset>
          <label className="etiquette">
            {t("modelesRapport.ordre")}
            <select
              className="champ max-w-sm"
              value={form.ordre_constats}
              onChange={(e) =>
                setForm({ ...form, ordre_constats: e.target.value })
              }
            >
              {ORDRES.map((o) => (
                <option key={o} value={o}>
                  {t(`modelesRapport.ordres.${o}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="etiquette">
            {t("modelesRapport.pied")}
            <textarea
              className="champ"
              rows={2}
              value={form.pied_de_page ?? ""}
              onChange={(e) =>
                setForm({ ...form, pied_de_page: e.target.value || null })
              }
            />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm">
              {tpl.logo
                ? t("modelesRapport.logoPresent")
                : t("modelesRapport.sansLogo")}
            </span>
            <label className="btn-secondaire cursor-pointer">
              {t("modelesRapport.choisirLogo")}
              <input
                type="file"
                accept="image/png,image/jpeg"
                className="sr-only"
                onChange={(e) =>
                  e.target.files?.[0] && void uploadLogo(e.target.files[0])
                }
              />
            </label>
            {tpl.logo && (
              <button
                type="button"
                className="underline"
                onClick={() =>
                  void run(
                    () =>
                      api(`/mission-report-templates/${tpl.id}/logo`, {
                        method: "DELETE",
                      }),
                    t("modelesRapport.logoRetire"),
                  )
                }
              >
                {t("modelesRapport.retirerLogo")}
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn-primaire">
              {t("modelesRapport.enregistrer")}
            </button>
            {!tpl.par_defaut && (
              <button
                type="button"
                className="btn-secondaire"
                onClick={() =>
                  void run(
                    () => post(`/mission-report-templates/${tpl.id}/default`),
                    t("modelesRapport.defautFait"),
                  )
                }
              >
                {t("modelesRapport.rendreDefaut")}
              </button>
            )}
            {!tpl.par_defaut && (
              <button
                type="button"
                className="underline"
                onClick={() =>
                  void run(async () => {
                    await del(`/mission-report-templates/${tpl.id}`);
                    setCurrent(null);
                    setForm(null);
                  }, t("modelesRapport.supprime"))
                }
              >
                {t("modelesRapport.supprimer")}
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}
