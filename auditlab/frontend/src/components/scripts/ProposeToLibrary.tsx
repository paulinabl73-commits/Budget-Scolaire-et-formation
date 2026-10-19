import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, post, put } from "../../api/client";
import type { ScriptInfo, ScriptTemplateInfo } from "../../api/scripts";
import Alert from "../Alert";

/** Proposition d'un script de mission à la bibliothèque, en brouillon (DAT-28). */
export default function ProposeToLibrary({
  script,
  code,
}: {
  script: ScriptInfo;
  code: string;
}) {
  const { t } = useTranslation();
  const [cycles, setCycles] = useState<Record<string, string>>({});
  const [form, setForm] = useState({
    reference: script.modele?.reference ?? "",
    cycle: "",
    nom: script.nom,
    objectif: script.description ?? "",
    colonnes: "",
    indicateur: "",
  });
  const [message, setMessage] = useState<{
    kind: "erreur" | "succes";
    text: string;
  } | null>(null);
  useEffect(() => {
    api<Record<string, string>>("/script-library/cycles").then(setCycles, () =>
      setCycles({}),
    );
  }, []);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = {
      ...form,
      code,
      objectif: form.objectif || null,
      indicateur: form.indicateur || null,
      colonnes: form.colonnes
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean),
    };
    try {
      if (script.modele) {
        // Nouvelle version du test dont le script est issu.
        const draft = await post<ScriptTemplateInfo>(
          `/script-library/${script.modele.id}/versions`,
        );
        await put(`/script-library/${draft.id}`, {
          ...body,
          reference: draft.reference,
        });
      } else {
        await post("/script-library", body);
      }
      setMessage({ kind: "succes", text: t("bibliothequeScripts.propose") });
    } catch (err) {
      setMessage({ kind: "erreur", text: (err as Error).message });
    }
  };
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: e.target.value });
  return (
    <details className="carte">
      <summary className="cursor-pointer text-base font-semibold">
        {script.modele
          ? t("bibliothequeScripts.nouvelleVersion", {
              reference: script.modele.reference,
            })
          : t("bibliothequeScripts.proposer")}
      </summary>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <form
        onSubmit={(e) => void submit(e)}
        className="mt-2 grid gap-2 md:grid-cols-3"
      >
        <label className="etiquette">
          {t("bibliothequeScripts.reference")}
          <input
            className="champ"
            required
            pattern="[A-Z]{2,5}-[0-9]{2,3}"
            disabled={!!script.modele}
            value={form.reference}
            onChange={set("reference")}
          />
        </label>
        <label className="etiquette">
          {t("bibliothequeScripts.cycle")}
          <select
            className="champ"
            required
            value={form.cycle}
            onChange={set("cycle")}
          >
            <option value="">—</option>
            {Object.entries(cycles).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="etiquette">
          {t("scripts.col.nom")}
          <input
            className="champ"
            required
            minLength={3}
            value={form.nom}
            onChange={set("nom")}
          />
        </label>
        <label className="etiquette md:col-span-3">
          {t("bibliothequeScripts.objectif")}
          <input
            className="champ"
            value={form.objectif}
            onChange={set("objectif")}
          />
        </label>
        <label className="etiquette md:col-span-2">
          {t("bibliothequeScripts.colonnesSaisie")}
          <input
            className="champ"
            value={form.colonnes}
            onChange={set("colonnes")}
          />
        </label>
        <label className="etiquette">
          {t("bibliothequeScripts.indicateur")}
          <input
            className="champ"
            value={form.indicateur}
            onChange={set("indicateur")}
          />
        </label>
        <div className="md:col-span-3">
          <button type="submit" className="btn-primaire">
            {t("bibliothequeScripts.envoyer")}
          </button>
        </div>
      </form>
    </details>
  );
}
