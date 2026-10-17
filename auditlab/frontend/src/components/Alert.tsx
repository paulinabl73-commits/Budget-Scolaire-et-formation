import type { ReactNode } from "react";

// Noms de classes écrits en entier pour que Tailwind les conserve au build.
const CLASSES = {
  erreur: "alerte-erreur",
  info: "alerte-info",
  succes: "alerte-succes",
} as const;

export default function Alert({
  kind,
  children,
}: {
  kind: keyof typeof CLASSES;
  children: ReactNode;
}) {
  return (
    <div role={kind === "erreur" ? "alert" : "status"} className={CLASSES[kind]}>
      {children}
    </div>
  );
}
