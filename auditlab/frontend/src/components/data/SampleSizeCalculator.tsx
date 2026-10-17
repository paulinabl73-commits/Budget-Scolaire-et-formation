import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { post } from "../../api/client";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface SizeOut {
  taille: number;
  facteur_confiance: number;
  facteur_expansion: string | null;
  intervalle: string | null;
  methode: string;
}

const num = (v: string) => v.replace(/\s/g, "").replace(",", ".");

/** Calcul de la taille d'échantillon (DAT-21) ; la taille trouvée peut être reprise. */
export default function SampleSizeCalculator({ population, onUse }: { population?: string; onUse: (n: number) => void }) {
  const { t } = useTranslation();
  const [type, setType] = useState<"mus" | "attributs">("mus");
  const [confiance, setConfiance] = useState("95");
  const [pop, setPop] = useState(population ?? "");
  // Montant repris des totaux de contrôle quand le champ montant est choisi.
  useEffect(() => {
    if (population) setPop(population);
  }, [population]);
  const [tolerable, setTolerable] = useState("");
  const [attendu, setAttendu] = useState("0");
  const [res, setRes] = useState<SizeOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  const compute = async () => {
    setError(null);
    setRes(null);
    const c = String(Number(num(confiance)) / 100);
    const body =
      type === "mus"
        ? { type, confiance: c, population: num(pop), erreur_tolerable: num(tolerable), erreur_attendue: num(attendu) || "0" }
        : { type, confiance: c, taux_tolerable: String(Number(num(tolerable)) / 100), taux_attendu: String(Number(num(attendu) || "0") / 100) };
    try {
      setRes(await post<SizeOut>("/sampling/size", body));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const unit = type === "mus" ? "" : " (%)";
  return (
    <fieldset className="md:col-span-2 space-y-2 rounded border border-slate-200 p-3">
      <legend className="etiquette px-1">{t("taille.titre")}</legend>
      <div className="grid gap-2 md:grid-cols-5">
        <div>
          <label htmlFor="ts-type" className="etiquette">{t("taille.type")}</label>
          <select id="ts-type" className="champ" value={type} onChange={(e) => setType(e.target.value as "mus" | "attributs")}>
            <option value="mus">{t("taille.mus")}</option>
            <option value="attributs">{t("taille.attributs")}</option>
          </select>
        </div>
        <div>
          <label htmlFor="ts-conf" className="etiquette">{t("taille.confiance")}</label>
          <input id="ts-conf" className="champ" inputMode="decimal" value={confiance} onChange={(e) => setConfiance(e.target.value)} />
        </div>
        {type === "mus" && (
          <div>
            <label htmlFor="ts-pop" className="etiquette">{t("taille.population")}</label>
            <input id="ts-pop" className="champ" inputMode="decimal" value={pop} onChange={(e) => setPop(e.target.value)} />
          </div>
        )}
        <div>
          <label htmlFor="ts-tol" className="etiquette">{t("taille.tolerable")}{unit}</label>
          <input id="ts-tol" className="champ" inputMode="decimal" value={tolerable} onChange={(e) => setTolerable(e.target.value)} />
        </div>
        <div>
          <label htmlFor="ts-att" className="etiquette">{t("taille.attendue")}{unit}</label>
          <input id="ts-att" className="champ" inputMode="decimal" value={attendu} onChange={(e) => setAttendu(e.target.value)} />
        </div>
      </div>
      <button type="button" className="btn-secondaire" onClick={compute}>{t("taille.calculer")}</button>
      {error && <Alert kind="erreur">{error}</Alert>}
      {res && (
        <div className="flex flex-wrap items-center gap-3 text-sm" aria-live="polite">
          <strong>{t("taille.resultat", { n: formatNombre(res.taille) })}</strong>
          <span className="text-slate-600">
            {t("taille.facteur", { f: formatNombre(res.facteur_confiance) })}
            {res.intervalle && ` · ${t("taille.intervalle", { i: formatNombre(Number(res.intervalle)) })}`}
          </span>
          <button type="button" className="text-marque-700 underline" onClick={() => onUse(res.taille)}>{t("taille.utiliser")}</button>
        </div>
      )}
    </fieldset>
  );
}
