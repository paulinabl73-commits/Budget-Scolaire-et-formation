import { formatDateHeure, formatNombre, resumeJson } from "../lib/format";
import { can } from "../lib/permissions";

describe("formats français", () => {
  it("formate les nombres avec séparateur de milliers et virgule", () => {
    expect(formatNombre(1234567.5).replace(/\s/g, " ")).toBe("1 234 567,5");
  });

  it("formate les dates jj/mm/aaaa", () => {
    expect(formatDateHeure("2027-01-15T10:20:30Z")).toMatch(/^15\/01\/2027 \d{2}:20:30$/);
    expect(formatDateHeure(null)).toBe("");
    expect(formatDateHeure("pas une date")).toBe("");
  });

  it("résume un objet du journal", () => {
    expect(resumeJson({ nom: "Achats", actif: true, n: { a: 1 } })).toBe(
      'nom : Achats · actif : true · n : {"a":1}',
    );
    expect(resumeJson(null)).toBe("");
  });
});

describe("droits côté interface", () => {
  it("vérifie la présence d'une permission", () => {
    expect(can(["users:manage"], "users:manage")).toBe(true);
    expect(can(["data:read"], "users:manage")).toBe(false);
    expect(can(undefined, "users:manage")).toBe(false);
  });
});
