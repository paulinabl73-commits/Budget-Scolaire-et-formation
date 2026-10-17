import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import fr from "./fr.json";

// NF-13 : tous les textes sont externalisés ; ajouter une langue = ajouter un fichier.
void i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr } },
  lng: "fr",
  fallbackLng: "fr",
  interpolation: { escapeValue: false },
});

export default i18n;
