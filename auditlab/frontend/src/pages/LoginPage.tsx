import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";

export default function LoginPage() {
  const { t } = useTranslation();
  const { user, login, sessionExpired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needCode, setNeedCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await login(email, password, needCode ? code : undefined);
      const from = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(result.mfa_enrollment_required ? "/double-authentification" : from, {
        replace: true,
      });
    } catch (err) {
      if (err instanceof ApiError && err.message === "mfa_required") {
        setNeedCode(true);
      } else {
        setError(err instanceof Error ? err.message : t("commun.erreurInconnue"));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-marque-900 px-4">
      <div className="carte w-full max-w-md">
        <p className="text-2xl font-semibold text-marque-900">{t("app.nom")}</p>
        <p className="mb-6 text-sm text-slate-600">{t("app.baseline")}</p>
        <h1 className="mb-4 text-lg font-semibold">{t("connexion.titre")}</h1>
        {sessionExpired && (
          <div className="mb-4">
            <Alert kind="info">{t("connexion.sessionExpiree")}</Alert>
          </div>
        )}
        {error && (
          <div className="mb-4">
            <Alert kind="erreur">{error}</Alert>
          </div>
        )}
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="etiquette">
              {t("connexion.email")}
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              className="champ"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={needCode}
            />
          </div>
          <div>
            <label htmlFor="password" className="etiquette">
              {t("connexion.motDePasse")}
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              className="champ"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={needCode}
            />
          </div>
          {needCode && (
            <div>
              <label htmlFor="totp" className="etiquette">
                {t("connexion.codeTotp")}
              </label>
              <input
                id="totp"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                required
                autoFocus
                aria-describedby="totp-aide"
                className="champ tracking-widest"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              />
              <p id="totp-aide" className="mt-1 text-xs text-slate-600">
                {t("connexion.codeTotpAide")}
              </p>
            </div>
          )}
          <button type="submit" className="btn-primaire w-full" disabled={busy}>
            {needCode ? t("connexion.verifier") : t("connexion.seConnecter")}
          </button>
        </form>
      </div>
    </main>
  );
}
