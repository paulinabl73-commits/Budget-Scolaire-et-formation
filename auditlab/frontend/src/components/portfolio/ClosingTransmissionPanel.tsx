import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import { formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

interface Transmission {
  transmis_le: string | null;
  transmis_par: string | null;
  mission: string | null;
  reprises: { dossier_id: string; mission: string }[];
}

/** Transmission du dossier de clôture à la mission d'audit de l'entité (RCO-27). */
export default function ClosingTransmissionPanel({
  closingId,
  canManage,
  visaExpert,
}: {
  closingId: string;
  canManage: boolean;
  visaExpert: boolean;
}) {
  const { t } = useTranslation();
  const [data, setData] = useState<Transmission | null>(null);
  const [mission, setMission] = useState("");
  const [error, setError] = useState<string | null>(null);
  const url = `/closings/${closingId}/transmission`;
  useEffect(() => {
    api<Transmission>(url).then(setData, (e: Error) => setError(e.message));
  }, [url]);
  const run = async (action: () => Promise<Transmission>) => {
    setError(null);
    try {
      setData(await action());
    } catch (e) {
      setError((e as Error).message);
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const taken = data.reprises[0];
  return (
    <section
      className="carte space-y-2 text-sm"
      aria-labelledby={`tr-${closingId}`}
    >
      <h2 id={`tr-${closingId}`} className="text-base font-semibold">
        {t("transmissionCloture.titre")}
      </h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <p className="text-slate-700">{t("transmissionCloture.aide")}</p>
      {taken ? (
        <p className="font-medium">
          {t("transmissionCloture.repris", { mission: taken.mission })}
        </p>
      ) : data.transmis_le ? (
        <p className="font-medium">
          {t("transmissionCloture.transmis", {
            mission: data.mission,
            par: data.transmis_par,
            le: formatDateHeure(data.transmis_le),
          })}
        </p>
      ) : (
        <p>{t("transmissionCloture.nonTransmis")}</p>
      )}
      {canManage && !taken && !visaExpert && (
        <p className="text-slate-700">{t("transmissionCloture.visaAttendu")}</p>
      )}
      {canManage && !taken && visaExpert && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => post<Transmission>(url, { mission }));
          }}
        >
          <label className="etiquette">
            {t("transmissionCloture.mission")}
            <input
              className="champ"
              required
              minLength={3}
              value={mission}
              onChange={(e) => setMission(e.target.value)}
            />
          </label>
          <button type="submit" className="btn-primaire">
            {t("transmissionCloture.transmettre")}
          </button>
          {data.transmis_le && (
            <button
              type="button"
              className="underline"
              onClick={() =>
                void run(() => del(url).then(() => api<Transmission>(url)))
              }
            >
              {t("transmissionCloture.retirer")}
            </button>
          )}
        </form>
      )}
    </section>
  );
}
