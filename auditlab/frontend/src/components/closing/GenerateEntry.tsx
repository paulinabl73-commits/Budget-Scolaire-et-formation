import { useState } from "react";
import { useTranslation } from "react-i18next";

import { post } from "../../api/client";
import Alert from "../Alert";

/** Bouton commun des assistants : propose l'écriture d'inventaire (RCO-11 à RCO-16). */
export default function GenerateEntry({ url, disabled }: { url: string; disabled?: boolean }) {
  const { t } = useTranslation();
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setError(null);
    setDone(null);
    try {
      const r = await post<{ numero: number; total: string }>(url);
      setDone(t("inventaire.ecritureProposee", { numero: r.numero }));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="space-y-2">
      <button type="button" className="btn-primaire" disabled={disabled} onClick={() => void run()}>{t("inventaire.generer")}</button>
      {done && <Alert kind="succes">{done}</Alert>}
      {error && <Alert kind="erreur">{error}</Alert>}
    </div>
  );
}
