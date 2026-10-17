import { useTranslation } from "react-i18next";

import type { Criticality } from "../../api/types";

const COLORS: Record<Criticality, string> = {
  faible: "bg-emerald-100 text-emerald-800",
  moyenne: "bg-amber-100 text-amber-800",
  elevee: "bg-orange-100 text-orange-800",
  critique: "bg-red-100 text-red-800",
};

/** Criticité d'un constat (CON-02), libellé et couleur. */
export default function CriticalityBadge({ value }: { value: Criticality }) {
  const { t } = useTranslation();
  return <span className={`rounded px-2 py-0.5 text-xs font-semibold ${COLORS[value]}`}>{t(`constats.criticites.${value}`)}</span>;
}
