import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download, put } from "../../api/client";
import type { Engagement } from "../../api/types";
import Alert from "../Alert";

export interface MissionReportInfo {
  id: string;
  template_id: string;
  modele: string;
  synthese: string | null;
  conclusion: string | null;
  peut_rediger: boolean;
}

/** Rapport de mission (REP-02) : modèle, synthèse et conclusion, génération PDF et Word. */
export default function ReportTab({ mission }: { mission: Engagement }) {
  const { t } = useTranslation();
  const [report, setReport] = useState<MissionReportInfo | null>(null);
  const [templates, setTemplates] = useState<
    { id: string; nom: string; actif: boolean }[]
  >([]);
  const [form, setForm] = useState({
    template_id: "",
    synthese: "",
    conclusion: "",
  });
  const [message, setMessage] = useState<{
    kind: "erreur" | "succes";
    text: string;
  } | null>(null);
  const url = `/engagements/${mission.id}/report`;
  const apply = (r: MissionReportInfo) => {
    setReport(r);
    setForm({
      template_id: r.template_id,
      synthese: r.synthese ?? "",
      conclusion: r.conclusion ?? "",
    });
  };
  const load = useCallback(
    () => api<MissionReportInfo>(url).then(apply),
    [url],
  );
  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
    api<{ id: string; nom: string; actif: boolean }[]>(
      "/mission-report-templates",
    ).then(
      (l) => setTemplates(l.filter((x) => x.actif)),
      () => setTemplates([]),
    );
  }, [load]);
  if (!report)
    return message ? <Alert kind={message.kind}>{message.text}</Alert> : null;
  const save = async () => {
    setMessage(null);
    try {
      apply(
        await put<MissionReportInfo>(url, {
          template_id: form.template_id || null,
          synthese: form.synthese || null,
          conclusion: form.conclusion || null,
        }),
      );
      setMessage({ kind: "succes", text: t("rapportMission.enregistre") });
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
    }
  };
  const get = (fmt: string) =>
    void download(
      `${url}/document?format=${fmt}`,
      undefined,
      `rapport_${mission.reference}.${fmt}`,
    ).catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
  const editable = report.peut_rediger;
  return (
    <div className="space-y-4">
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <section className="carte space-y-3" aria-labelledby="rapport-redaction">
        <h2 id="rapport-redaction" className="text-base font-semibold">
          {t("rapportMission.titre")}
        </h2>
        <label className="etiquette">
          {t("rapportMission.modele")}
          <select
            className="champ max-w-md"
            disabled={!editable}
            value={form.template_id}
            onChange={(e) => setForm({ ...form, template_id: e.target.value })}
          >
            {templates.map((m) => (
              <option key={m.id} value={m.id}>
                {m.nom}
              </option>
            ))}
            {!templates.some((m) => m.id === form.template_id) && (
              <option value={form.template_id}>{report.modele}</option>
            )}
          </select>
        </label>
        <label className="etiquette">
          {t("rapportMission.synthese")}
          <textarea
            className="champ"
            rows={6}
            disabled={!editable}
            value={form.synthese}
            onChange={(e) => setForm({ ...form, synthese: e.target.value })}
          />
        </label>
        <label className="etiquette">
          {t("rapportMission.conclusion")}
          <textarea
            className="champ"
            rows={3}
            disabled={!editable}
            value={form.conclusion}
            onChange={(e) => setForm({ ...form, conclusion: e.target.value })}
          />
        </label>
        <p className="text-xs text-slate-600">{t("rapportMission.aide")}</p>
        <div className="flex flex-wrap gap-2">
          {editable && (
            <button
              type="button"
              className="btn-primaire"
              onClick={() => void save()}
            >
              {t("rapportMission.enregistrer")}
            </button>
          )}
          <button
            type="button"
            className="btn-secondaire"
            onClick={() => get("pdf")}
          >
            {t("rapportMission.pdf")}
          </button>
          <button
            type="button"
            className="btn-secondaire"
            onClick={() => get("docx")}
          >
            {t("rapportMission.word")}
          </button>
        </div>
      </section>
    </div>
  );
}
