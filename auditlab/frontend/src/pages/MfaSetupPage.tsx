import { QRCodeSVG } from "qrcode.react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { post } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";

interface Setup {
  secret: string;
  provisioning_uri: string;
}

export default function MfaSetupPage() {
  const { t } = useTranslation();
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const requested = useRef(false);

  useEffect(() => {
    if (user?.mfa_enabled || requested.current) return;
    requested.current = true;
    post<Setup>("/auth/mfa/setup")
      .then(setSetup)
      .catch((e: Error) => setError(e.message));
  }, [user?.mfa_enabled]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await post("/auth/mfa/activate", { code });
      await refresh();
      navigate("/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    }
  };

  if (user?.mfa_enabled) return <Alert kind="succes">{t("mfa.active")}</Alert>;

  return (
    <div className="mx-auto max-w-lg p-8">
      <div className="carte space-y-4">
        <h1 className="text-xl font-semibold">{t("mfa.titre")}</h1>
        <p className="text-sm text-slate-700">{t("mfa.intro")}</p>
        {error && <Alert kind="erreur">{error}</Alert>}
        {setup && (
          <>
            <div className="flex justify-center">
              <QRCodeSVG value={setup.provisioning_uri} size={180} title={t("mfa.titre")} />
            </div>
            <p className="text-sm">
              {t("mfa.cleManuelle")} : <code className="break-all font-mono">{setup.secret}</code>
            </p>
            <form onSubmit={onSubmit} className="space-y-3">
              <label htmlFor="code" className="etiquette">
                {t("connexion.codeTotp")}
              </label>
              <input
                id="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                className="champ tracking-widest"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              />
              <button type="submit" className="btn-primaire" disabled={code.length !== 6}>
                {t("mfa.activer")}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
