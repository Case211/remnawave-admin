// @ts-nocheck
import React, { useRef, useEffect, useMemo } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, drawSelection, highlightActiveLine, dropCursor,
         rectangularSelection, highlightSpecialChars, crosshairCursor,
         lineNumbers, highlightActiveLineGutter } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { indentOnInput, syntaxHighlighting, defaultHighlightStyle, bracketMatching, foldGutter, foldKeymap } from "@codemirror/language";
import { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
import { autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap } from "@codemirror/autocomplete";
import { lintKeymap, linter, lintGutter } from "@codemirror/lint";
import { jsonLanguage, json } from "@codemirror/lang-json";
import { oneDark } from "@codemirror/theme-one-dark";
import Ajv from "ajv";
import xraySchema from "../../utils/config.schema.json";

const ajv = new Ajv({ allErrors: true, strict: false });

interface JsonEditorProps {
    value: string;
    onChange: (value: string) => void;
    readOnly?: boolean;
    schemaMode?: 'full' | 'inbound' | 'inbounds' | 'outbound' | 'outbounds' | 'rule' | 'dns' | 'balancer' | 'routing';
    mode?: 'json' | 'plaintext';
}

export const JsonEditor = ({ value, onChange, readOnly = false, schemaMode = 'full', mode = 'json' }: JsonEditorProps) => {
    const editorParent = useRef<HTMLDivElement>(null);
    const viewRef = useRef<EditorView | null>(null);

    const isJson = mode === 'json';

    // Подготовка схемы
    const schemaForMode = useMemo(() => {
        if (!isJson) return null;
        if (schemaMode === 'full') return xraySchema;
        let refPath = "";
        switch (schemaMode) {
            case 'inbound': refPath = "InboundObject"; break;
            case 'outbound': refPath = "OutboundObject"; break;
            case 'rule': refPath = "RoutingRule"; break;
            case 'routing': refPath = "RoutingObject"; break;
            case 'dns': refPath = "DnsObject"; break;
            case 'balancer': refPath = "BalancerObject"; break;
            case 'inbounds': return { ...xraySchema, $ref: undefined, type: "array", items: { $ref: "#/definitions/InboundObject" } };
            case 'outbounds': return { ...xraySchema, $ref: undefined, type: "array", items: { $ref: "#/definitions/OutboundObject" } };
            default: return xraySchema;
        }
        return { ...xraySchema, $ref: `#/definitions/${refPath}` };
    }, [schemaMode, isJson]);

    // Единый линтер (синтаксис + схема)
    const customLinter = useMemo(() => {
        if (!isJson || !schemaForMode) return null;
        const validate = ajv.compile(schemaForMode);
        return linter((view) => {
            const diagnostics: any[] = [];
            const doc = view.state.doc.toString();
            if (!doc.trim()) return [];

            try {
                const cleanJson = doc.replace(/("(?:\\.|[^\\"])*")|\/\*[\s\S]*?\*\/|\/\/.*/g, (match, group1) => group1 || "");
                const parsed = JSON.parse(cleanJson);
                const valid = validate(parsed);

                if (!valid && validate.errors) {
                    validate.errors.forEach(err => {
                        diagnostics.push({
                            from: 0, to: view.state.doc.length,
                            severity: "error",
                            message: `Schema: ${err.instancePath} ${err.message}`,
                        });
                    });
                }
            } catch (e: any) {
                diagnostics.push({
                    from: 0, to: view.state.doc.length,
                    severity: "error",
                    message: e.message || "Invalid JSON syntax",
                });
            }
            return diagnostics;
        });
    }, [schemaForMode, isJson]);

    // --- УЛУЧШЕННАЯ АВТОПОДСТАНОВКА (COMPLETION) ---
    const customCompletion = useMemo(() => {
        if (!isJson) return null;
        return jsonLanguage.data.of({
            autocomplete: (context: any) => {
                const word = context.matchBefore(/[\w"]*/);
                if (!word || (word.from === word.to && !context.explicit)) return null;

                const doc = context.state.doc.toString();
                const options: any[] = [];
                const definitions: any = xraySchema.definitions || {};
                
                // Функция для рекурсивного поиска ключей в схеме
                const getKeysFromSchema = (schema: any): string[] => {
                    if (!schema) return [];
                    if (schema.$ref) {
                        const ref = schema.$ref.split('/').pop();
                        return getKeysFromSchema(definitions[ref]);
                    }
                    if (schema.properties) return Object.keys(schema.properties);
                    if (schema.items) return getKeysFromSchema(schema.items);
                    return [];
                };

                // Определяем текущий набор ключей
                const availableKeys = getKeysFromSchema(schemaForMode);
                
                availableKeys.forEach(key => {
                    options.push({ 
                        label: `"${key}"`, 
                        type: "property", 
                        apply: `"${key}": `,
                        detail: "schema property"
                    });
                });

                // Добавляем значения для протоколов, если мы в поле "protocol"
                const line = doc.slice(0, context.pos).split('\n').pop() || "";
                if (line.includes('"protocol"')) {
                    const protocols = ["vless", "vmess", "trojan", "shadowsocks", "hysteria", "hysteria2", "socks", "http", "wireguard", "freedom", "blackhole"];
                    protocols.forEach(p => options.push({ label: `"${p}"`, type: "keyword", detail: "protocol" }));
                }

                return {
                    from: word.from,
                    options: options,
                    filter: false // Позволяем CodeMirror самому фильтровать по вводу
                };
            }
        });
    }, [schemaForMode, isJson]);

    useEffect(() => {
        if (!editorParent.current) return;

        const extensions = [
            lineNumbers(),
            highlightActiveLineGutter(),
            highlightSpecialChars(),
            history(),
            foldGutter(),
            drawSelection(),
            dropCursor(),
            EditorState.allowMultipleSelections.of(true),
            indentOnInput(),
            syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
            bracketMatching(),
            closeBrackets(),
            rectangularSelection(),
            crosshairCursor(),
            highlightActiveLine(),
            highlightSelectionMatches(),
            keymap.of([
                ...closeBracketsKeymap,
                ...defaultKeymap,
                ...searchKeymap,
                ...historyKeymap,
                ...foldKeymap,
                ...completionKeymap,
                ...lintKeymap
            ]),
            oneDark,
            EditorView.updateListener.of((update) => {
                if (update.docChanged) {
                    onChange(update.state.doc.toString());
                }
            }),
            EditorView.editable.of(!readOnly),
            EditorState.readOnly.of(readOnly),
            EditorView.theme({
                "&": { height: "100%", backgroundColor: "#1e1e1e" },
                "&.cm-focused": { outline: "none" },
                ".cm-scroller": {
                    overflow: "auto !important",
                    scrollbarWidth: "thin",
                    scrollbarColor: "#334155 #0f172a",
                    height: "100%",
                    maxHeight: "100%"
                },
                ".cm-scroller::-webkit-scrollbar": {
                    width: "10px",
                    height: "10px"
                },
                ".cm-scroller::-webkit-scrollbar-track": {
                    background: "#0f172a"
                },
                ".cm-scroller::-webkit-scrollbar-thumb": {
                    background: "#334155",
                    borderRadius: "10px",
                    border: "3px solid #0f172a"
                },
                ".cm-scroller::-webkit-scrollbar-thumb:hover": {
                    background: "#475569"
                },
                ".cm-gutters": {
                    backgroundColor: "#1e1e1e",
                    color: "#6b7280",
                    border: "none"
                },
                ".cm-activeLineGutter": {
                    backgroundColor: "#2d3748",
                    color: "#e2e8f0"
                },
                ".cm-tooltip": {
                    backgroundColor: "#1e293b",
                    border: "1px solid #334155",
                    borderRadius: "6px",
                    boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.5)"
                },
                ".cm-tooltip-autocomplete > ul > li[aria-selected]": {
                    backgroundColor: "#312e81",
                    color: "white"
                }
            })
        ];

        if (isJson) {
            extensions.push(
                json(),
                autocompletion({
                    defaultKeymap: true,
                    aboveCursor: true,
                    activateOnTyping: true,
                    icons: true
                }),
                customCompletion!,
                lintGutter(),
                customLinter!
            );
        }

        const state = EditorState.create({
            doc: value,
            extensions
        });

        const view = new EditorView({
            state,
            parent: editorParent.current
        });

        viewRef.current = view;

        return () => {
            view.destroy();
        };
    }, [schemaMode, readOnly]); 

    useEffect(() => {
        if (viewRef.current && value !== viewRef.current.state.doc.toString()) {
            viewRef.current.dispatch({
                changes: { from: 0, to: viewRef.current.state.doc.length, insert: value }
            });
        }
    }, [value]);

    return (
        <div 
            ref={editorParent} 
            className="h-full w-full bg-[#1e1e1e] overflow-hidden flex flex-col font-mono text-[13px] border border-slate-700 rounded-lg shadow-inner"
        >
            <style>{`
                .cm-editor { height: 100% !important; outline: none !important; }
                .cm-scroller { font-family: 'JetBrains Mono', monospace !important; }
                .cm-content { padding-bottom: 100px !important; }
                .cm-gutterElement { font-size: 11px; opacity: 0.5; }
                /* Исправление отображения ошибок */
                .cm-lintRange-error { background-image: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="6" height="3">%3Cpath d="M0 3 L3 0 L6 3" fill="none" stroke="%23f87171" stroke-width="1"/%3E</svg>'); background-position: bottom left; background-repeat: repeat-x; }
            `}</style>
        </div>
    );
};