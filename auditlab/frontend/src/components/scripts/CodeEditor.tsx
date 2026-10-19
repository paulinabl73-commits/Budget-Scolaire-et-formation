import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

// Monaco servi par l'application (aucun chargement depuis un CDN) ; seul le worker de base
// est nécessaire pour Python (coloration syntaxique).
self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

/** Éditeur de code Python (DAT-26), chargé à la demande avec la page du script. */
export default function CodeEditor({
  value,
  onChange,
  readOnly,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  readOnly?: boolean;
  label: string;
}) {
  return (
    <div className="overflow-hidden rounded border border-slate-300">
      <Editor
        height="420px"
        language="python"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 13,
          tabSize: 4,
          insertSpaces: true,
          scrollBeyondLastLine: false,
          ariaLabel: label,
          wordWrap: "on",
        }}
      />
    </div>
  );
}
