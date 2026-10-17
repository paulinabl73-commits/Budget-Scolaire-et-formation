import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { post } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";

export default function ProfilePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(
    null,
  );

  if (!user) return null;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== confirm) {
      setMessage({ kind: "erreur", text: t("profil.differents") });
      return;
    }
    try {
      await post("/auth/password", { current_password: current, new_password: next });
      setMessage({ kind: "succes", text: t("profil.change") });
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setMessage({ kind: "erreur", text: (err as Error).message });
    }
  };

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-2xl font-semibold">{t("profil.titre")}</h1>
      <div className="carte space-y-1 text-sm">
        <p className="font-medium">{user.nom}</p>
        <p>{user.email}</p>
        <p>{t(`roles.${user.role}`)}</p>
        <p>{user.mfa_enabled ? t("profil.mfaActive") : t("profil.mfaInactive")}</p>
        {!user.mfa_enabled && (
          <Link to="/double-authentification" className="text-marque-700 underline">
            {t("profil.activerMfa")}
          </Link>
        )}
      </div>
      <form onSubmit={onSubmit} className="carte space-y-4">
        <h2 className="text-lg font-semibold">{t("profil.changerMotDePasse")}</h2>
        {message && <Alert kind={message.kind}>{message.text}</Alert>}
        {(
          [
            ["actuel", current, setCurrent, "current-password"],
            ["nouveau", next, setNext, "new-password"],
            ["confirmation", confirm, setConfirm, "new-password"],
          ] as const
        ).map(([key, value, setter, auto]) => (
          <div key={key}>
            <label htmlFor={`pw-${key}`} className="etiquette">
              {t(`profil.${key}`)}
            </label>
            <input
              id={`pw-${key}`}
              type="password"
              autoComplete={auto}
              required
              className="champ"
              value={value}
              onChange={(e) => setter(e.target.value)}
            />
          </div>
        ))}
        <button type="submit" className="btn-primaire">
          {t("commun.enregistrer")}
        </button>
      </form>
    </div>
  );
}
