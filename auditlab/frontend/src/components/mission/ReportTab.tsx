import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download, post, put } from "../../api/client";
import { formatDateHeure } from "../../lib/format";
import type { Engagement } from "../../api/types";
import Alert from "../Alert";

export interface MissionReportInfo {
  id: string;
  template_id: string;
  modele: string;
  synthese: string | null;
  conclusion: string | null;
  peut_rediger: boolean;
  statut: "projet" | "revu" | "valide" | "diffuse";
  historique: {
    de: string;
    vers: string;
    par: string;
    le: string;
    commentaire: string | null;
  }[];
  diffuse_le: string | null;
  empreintes: Record<string, string>;
  transitions: string[];
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
  const [motif, setMotif] = useState("");
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
  const move = async (statut: string) => {
    setMessage(null);
    try {
      apply(
        await post<MissionReportInfo>(`${url}/transition`, {
          statut,
          commentaire: motif || null,
        }),
      );
      setMotif("");
      setMessage({ kind: "succes", text: t(`rapportMission.fait.${statut}`) });
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
      <section className="carte space-y-3" aria-labelledby="rapport-circuit">
        <h2 id="rapport-circuit" className="text-base font-semibold">
          {t("rapportMission.circuit")}
        </h2>
        <ol className="flex flex-wrap gap-2 text-sm">
          {(["projet", "revu", "valide", "diffuse"] as const).map((s) => (
            <li
              key={s}
              aria-current={s === report.statut ? "step" : undefined}
              className={`rounded px-2 py-1 ${s === report.statut ? "bg-marque-600 text-white" : "bg-slate-100 text-slate-700"}`}
            >
              {t(`rapportMission.statuts.${s}`)}
            </li>
          ))}
        </ol>
        {report.statut === "diffuse" && report.diffuse_le && (
          <p className="text-sm">
            {t("rapportMission.fige", {
              le: formatDateHeure(report.diffuse_le),
              sha: (report.empreintes.pdf ?? "").slice(0, 16),
            })}
          </p>
        )}
        {report.transitions.length > 0 && (
          <div className="flex flex-wrap items-end gap-2">
            {report.transitions.includes("projet") && (
              <label className="etiquette">
                {t("rapportMission.motif")}
                <input
                  className="champ"
                  value={motif}
                  onChange={(e) => setMotif(e.target.value)}
                />
              </label>
            )}
            {report.transitions.map((s) => (
              <button
                key={s}
                type="button"
                className={s === "projet" ? "btn-secondaire" : "btn-primaire"}
                onClick={() => void move(s)}
              >
                {t(`rapportMission.actions.${s}`)}
              </button>
            ))}
          </div>
        )}
        {report.historique.length > 0 && (
          <ul className="space-y-1 text-sm text-slate-700">
            {report.historique.map((h) => (
              <li key={h.le}>
                {formatDateHeure(h.le)} · {h.par} :{" "}
                {t(`rapportMission.statuts.${h.de}`)} →{" "}
                {t(`rapportMission.statuts.${h.vers}`)}
                {h.commentaire && ` (${h.commentaire})`}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
