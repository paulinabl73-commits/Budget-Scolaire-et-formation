import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { del, upload } from "../../api/client";
import type { Attachment } from "../../api/types";
import { formatDateHeure, formatTaille } from "../../lib/format";
import Alert from "../Alert";

interface Props {
  workpaperId: string;
  attachments: Attachment[];
  editable: boolean;
  onChange: () => void;
}

export default function AttachmentsPanel({ workpaperId, attachments, editable, onChange }: Props) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(null);

  const send = async (file: File) => {
    setBusy(true);
    setMessage(null);
    try {
      await upload(`/workpapers/${workpaperId}/attachments`, file);
      setMessage({ kind: "succes", text: t("pieces.deposee") });
      onChange();
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  const remove = async (a: Attachment) => {
    if (!window.confirm(t("pieces.confirmerSuppression", { nom: a.nom_fichier }))) return;
    try {
      await del(`/attachments/${a.id}`);
      setMessage({ kind: "succes", text: t("pieces.supprimee") });
      onChange();
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
    }
  };

  return (
    <section className="carte space-y-3" aria-labelledby="pj-titre">
      <h2 id="pj-titre" className="text-base font-semibold">{t("pieces.titre")}</h2>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {editable && (
        <div>
          <label htmlFor="pj-file" className="etiquette">{t("pieces.deposer")}</label>
          <input id="pj-file" ref={input} type="file" disabled={busy} aria-describedby="pj-aide"
            accept=".pdf,.xlsx,.xls,.docx,.csv,.txt,.png,.jpg,.jpeg,.gif,.webp"
            className="mt-1 block text-sm" onChange={(e) => e.target.files?.[0] && send(e.target.files[0])} />
          <p id="pj-aide" className="mt-1 text-xs text-slate-600">{busy ? t("pieces.envoi") : t("pieces.aide")}</p>
        </div>
      )}
      {attachments.length === 0 ? (
        <p className="text-sm text-slate-600">{t("pieces.aucune")}</p>
      ) : (
        <ul className="divide-y divide-slate-200 text-sm">
          {attachments.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 py-2">
              <span>
                <a href={a.url} target="_blank" rel="noreferrer" className="text-marque-700 underline">{a.nom_fichier}</a>{" "}
                <span className="text-xs text-slate-600">
                  {t("pieces.version", { version: a.version })} · {formatTaille(a.taille)} · {formatDateHeure(a.created_at)}
                </span>
                <span className="block font-mono text-[11px] text-slate-600" title={t("pieces.empreinte")}>
                  SHA-256 {a.sha256.slice(0, 16)}…
                </span>
              </span>
              {editable && (
                <button type="button" className="text-xs text-red-800 underline" onClick={() => remove(a)}>{t("commun.supprimer")}</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
