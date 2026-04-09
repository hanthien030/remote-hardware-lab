import Editor, { type Monaco } from '@monaco-editor/react';
import React, { useEffect, useRef, useState } from 'react';
import type { editor } from 'monaco-editor';
import '../styles/CodeEditor.css';

export interface CompileEditorMarker {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
  message: string;
}

interface CodeEditorProps {
  language?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string;
  path?: string;
  markers?: CompileEditorMarker[];
}

export const CodeEditor: React.FC<CodeEditorProps> = ({
  language = 'cpp',
  defaultValue = '// Gõ code cho ESP32/Arduino tại đây\n\nvoid setup() {\n  Serial.begin(115200);\n}\n\nvoid loop() {\n  Serial.println("Hello ESP32");\n  delay(1000);\n}',
  onChange,
  readOnly = false,
  height = '400px',
  path,
  markers = [],
}) => {
  const [code, setCode] = useState(defaultValue ?? '');
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);

  const handleChange = (value: string | undefined) => {
    if (value !== undefined) {
      setCode(value);
      onChange?.(value);
    }
  };

  useEffect(() => {
    const editorInstance = editorRef.current;
    const monacoInstance = monacoRef.current;
    const model = editorInstance?.getModel();
    if (!monacoInstance || !model) return;

    monacoInstance.editor.setModelMarkers(
      model,
      'compile',
      markers.map(marker => ({
        ...marker,
        severity: monacoInstance.MarkerSeverity.Error,
      }))
    );
  }, [markers]);

  return (
    <div className="code-editor-container">
      <div className="editor-header">
        <div className="editor-title">
          <span className="lang-badge">{language.toUpperCase()}</span>
          <span className="editor-label">Code Editor</span>
        </div>
        <div className="editor-actions">
          <button
            className="btn-copy"
            onClick={() => {
              navigator.clipboard.writeText(code);
              alert('Code copied to clipboard!');
            }}
            title="Copy code"
          >
            📋 Copy
          </button>
        </div>
      </div>
      <Editor
        height={height}
        language={language}
        path={path}
        value={code}
        onChange={handleChange}
        onMount={(editorInstance, monacoInstance) => {
          editorRef.current = editorInstance;
          monacoRef.current = monacoInstance;

          const model = editorInstance.getModel();
          if (!model) return;

          monacoInstance.editor.setModelMarkers(
            model,
            'compile',
            markers.map(marker => ({
              ...marker,
              severity: monacoInstance.MarkerSeverity.Error,
            }))
          );
        }}
        theme="vs-dark"
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 14,
          fontFamily: "'Fira Code', 'Courier New', monospace",
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          automaticLayout: true,
          wordWrap: 'on',
        }}
      />
    </div>
  );
};
