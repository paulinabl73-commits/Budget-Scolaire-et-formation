import { useState } from "react";
import { useTranslation } from "react-i18next";

import { download } from "../../api/client";

/** Export Excel d'un tableau de bord avec ses filtres (REP-08). */
export default function ExcelExport({
  path,
  filename,
}: {
  path: string;
  filename: string;
}) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        className="btn-secondaire"
        onClick={() =>
          void download(path, undefined, filename).catch((e: Error) =>
            setError(e.message),
          )
        }
      >
        {t("tableauxDeBord.excel")}
      </button>
      {error && (
        <span role="alert" className="text-sm text-red-700">
          {error}
        </span>
      )}
    </span>
  );
}
