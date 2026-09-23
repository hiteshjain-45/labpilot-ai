import { useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { EditorView } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";

const theme = EditorView.theme(
  {
    "&": { backgroundColor: "#ffffff", color: "#16302b" },
    ".cm-content": { fontFamily: "var(--font-code)", padding: "10px 0", caretColor: "#16302b" },
    ".cm-gutters": { backgroundColor: "#f2f5f3", color: "#71857f", border: "none", borderRight: "1px solid #cbd6d2" },
    ".cm-activeLine": { backgroundColor: "#f7f9ee" },
    ".cm-activeLineGutter": { backgroundColor: "#eef2df", color: "#16302b" },
    ".cm-cursor": { borderLeftColor: "#16302b" },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": { backgroundColor: "#fbe7a1" },
  },
  { dark: false }
);

const highlight = HighlightStyle.define([
  { tag: t.keyword, color: "#0b5d4b", fontWeight: "700" },
  { tag: [t.string, t.special(t.string)], color: "#8a4b00" },
  { tag: [t.number, t.bool, t.null], color: "#1f5fa8" },
  { tag: t.comment, color: "#71857f", fontStyle: "italic" },
  { tag: [t.function(t.variableName), t.definition(t.function(t.variableName))], color: "#1b5e7a", fontWeight: "600" },
  { tag: t.operator, color: "#4a605b" },
]);

export default function CodeEditor({ value, onChange, readOnly = false, minHeight = "340px" }) {
  const extensions = useMemo(
    () => [python(), theme, syntaxHighlighting(highlight), EditorView.contentAttributes.of({ "aria-label": "Python code editor" })],
    []
  );
  return (
    <div className="editor">
      <CodeMirror
        value={value}
        onChange={onChange}
        readOnly={readOnly}
        extensions={extensions}
        theme="none"
        minHeight={minHeight}
        indentWithTab
        basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: true, autocompletion: false, closeBrackets: true, bracketMatching: true }}
      />
    </div>
  );
}
