import Image from "@tiptap/extension-image";
import Link from "@tiptap/extension-link";
import Table from "@tiptap/extension-table";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import TableRow from "@tiptap/extension-table-row";
import Underline from "@tiptap/extension-underline";
import type { Extensions, JSONContent } from "@tiptap/react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { Attachment, RichDoc, WorkpaperSummary } from "../../api/types";

/** Image d'une pièce jointe : l'identifiant est conservé, le lien signé sert à l'affichage. */
const AttachmentImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      attachmentId: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-attachment-id"),
        renderHTML: (attrs) => (attrs.attachmentId ? { "data-attachment-id": attrs.attachmentId } : {}),
      },
    };
  },
});

export const BASE_EXTENSIONS: Extensions = [
  StarterKit.configure({ codeBlock: false }),
  Underline,
  Link.configure({ openOnClick: false, autolink: false, protocols: ["mailto"] }),
  Table.configure({ resizable: false }),
  TableRow,
  TableHeader,
  TableCell,
  AttachmentImage.configure({ inline: true }),
];

interface Props {
  value: RichDoc;
  editable: boolean;
  onChange: (doc: RichDoc) => void;
  images: Attachment[];
  workpapers: WorkpaperSummary[];
  missionId: string;
  extraExtensions?: Extensions;
  extraTools?: (editor: NonNullable<ReturnType<typeof useEditor>>) => ReactNode;
}

export default function RichEditor({ value, editable, onChange, images, workpapers, missionId, extraExtensions = [], extraTools }: Props) {
  const { t } = useTranslation();
  const [panel, setPanel] = useState<"none" | "image" | "link" | "paper">("none");
  const [href, setHref] = useState("https://");
  const editor = useEditor({
    extensions: [...BASE_EXTENSIONS, ...extraExtensions],
    content: value as JSONContent,
    editable,
    onUpdate: ({ editor: e }) => onChange(e.getJSON() as RichDoc),
    editorProps: {
      attributes: {
        class: "prose-travaux min-h-48 rounded-b-md border border-slate-400 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-marque-600",
        "aria-label": t("editeur.zone"),
        role: "textbox",
        "aria-multiline": "true",
      },
    },
  });

  // Rechargement externe (après enregistrement ou changement de papier).
  useEffect(() => {
    if (editor && JSON.stringify(editor.getJSON()) !== JSON.stringify(value)) {
      editor.commands.setContent(value as JSONContent, false);
    }
  }, [editor, value]);

  useEffect(() => {
    editor?.setEditable(editable);
  }, [editor, editable]);

  if (!editor) return null;
  const btn = (label: string, active: boolean, action: () => void, text?: string) => (
    <button type="button" title={label} aria-label={label} aria-pressed={active}
      className={`rounded px-2 py-1 text-sm ${active ? "bg-marque-600 text-white" : "hover:bg-slate-200"}`}
      onMouseDown={(e) => e.preventDefault()} onClick={action}>
      {text ?? label}
    </button>
  );
  const chain = () => editor.chain().focus();
  const inTable = editor.isActive("table");
  const pictures = images.filter((i) => i.content_type.startsWith("image/"));

  return (
    <div>
      {editable && (
        <div role="toolbar" aria-label={t("editeur.barre")}
          className="flex flex-wrap items-center gap-1 rounded-t-md border border-b-0 border-slate-400 bg-slate-50 px-2 py-1">
          {btn(t("editeur.gras"), editor.isActive("bold"), () => chain().toggleBold().run(), "G")}
          {btn(t("editeur.italique"), editor.isActive("italic"), () => chain().toggleItalic().run(), "I")}
          {btn(t("editeur.souligne"), editor.isActive("underline"), () => chain().toggleUnderline().run(), "S")}
          {btn(t("editeur.titre"), editor.isActive("heading"), () => chain().toggleHeading({ level: 3 }).run(), "T")}
          {btn(t("editeur.liste"), editor.isActive("bulletList"), () => chain().toggleBulletList().run(), "•")}
          {btn(t("editeur.listeNum"), editor.isActive("orderedList"), () => chain().toggleOrderedList().run(), "1.")}
          {btn(t("editeur.citation"), editor.isActive("blockquote"), () => chain().toggleBlockquote().run(), "❝")}
          <span className="mx-1 h-5 w-px bg-slate-300" aria-hidden />
          {btn(t("editeur.tableau"), false, () => chain().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(), "▦")}
          {inTable && btn(t("editeur.ligne"), false, () => chain().addRowAfter().run(), "+L")}
          {inTable && btn(t("editeur.colonne"), false, () => chain().addColumnAfter().run(), "+C")}
          {inTable && btn(t("editeur.supprLigne"), false, () => chain().deleteRow().run(), "−L")}
          {inTable && btn(t("editeur.supprColonne"), false, () => chain().deleteColumn().run(), "−C")}
          {inTable && btn(t("editeur.supprTableau"), false, () => chain().deleteTable().run(), "✕▦")}
          <span className="mx-1 h-5 w-px bg-slate-300" aria-hidden />
          {btn(t("editeur.image"), panel === "image", () => setPanel(panel === "image" ? "none" : "image"), "🖼")}
          {btn(t("editeur.lien"), editor.isActive("link"), () => setPanel(panel === "link" ? "none" : "link"), "🔗")}
          {btn(t("editeur.lienPapier"), panel === "paper", () => setPanel(panel === "paper" ? "none" : "paper"), "↗ PT")}
          {editor.isActive("link") && btn(t("editeur.annulerLien"), false, () => chain().unsetLink().run(), "⊘")}
          {extraTools?.(editor)}
          <span className="mx-1 h-5 w-px bg-slate-300" aria-hidden />
          {btn(t("editeur.defaire"), false, () => chain().undo().run(), "↶")}
          {btn(t("editeur.refaire"), false, () => chain().redo().run(), "↷")}
        </div>
      )}
      {editable && panel === "image" && (
        <div className="flex items-center gap-2 border border-b-0 border-slate-400 bg-white px-2 py-2">
          {pictures.length === 0 ? (
            <p className="text-xs text-slate-600">{t("editeur.aucuneImage")}</p>
          ) : (
            <select aria-label={t("editeur.image")} className="champ mt-0" defaultValue=""
              onChange={(e) => {
                const img = pictures.find((p) => p.id === e.target.value);
                if (img) {
                  chain().insertContent({ type: "image", attrs: { src: img.url, alt: img.nom_fichier, attachmentId: img.id } }).run();
                  setPanel("none");
                }
              }}>
              <option value="">{t("editeur.choisirImage")}</option>
              {pictures.map((p) => <option key={p.id} value={p.id}>{p.nom_fichier}</option>)}
            </select>
          )}
        </div>
      )}
      {editable && panel === "link" && (
        <form className="flex items-center gap-2 border border-b-0 border-slate-400 bg-white px-2 py-2"
          onSubmit={(e) => {
            e.preventDefault();
            chain().extendMarkRange("link").setLink({ href }).run();
            setPanel("none");
          }}>
          <input aria-label={t("editeur.adresse")} className="champ mt-0" value={href} onChange={(e) => setHref(e.target.value)} />
          <button type="submit" className="btn-secondaire">OK</button>
        </form>
      )}
      {editable && panel === "paper" && (
        <div className="flex items-center gap-2 border border-b-0 border-slate-400 bg-white px-2 py-2">
          <select aria-label={t("editeur.lienPapier")} className="champ mt-0" defaultValue=""
            onChange={(e) => {
              const wp = workpapers.find((w) => w.id === e.target.value);
              if (!wp) return;
              const target = `/missions/${missionId}/papiers/${wp.id}`;
              if (editor.state.selection.empty) {
                chain().insertContent({ type: "text", text: wp.reference, marks: [{ type: "link", attrs: { href: target } }] }).run();
              } else {
                chain().setLink({ href: target }).run();
              }
              setPanel("none");
            }}>
            <option value="">{t("editeur.choisirPapier")}</option>
            {workpapers.map((w) => <option key={w.id} value={w.id}>{w.reference} — {w.titre}</option>)}
          </select>
        </div>
      )}
      <EditorContent editor={editor} />
    </div>
  );
}
