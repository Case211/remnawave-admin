// @ts-nocheck
import React, { useState, useEffect } from "react";
import { JsonEditor } from "./JsonEditor";

interface JsonFieldProps {
    label?: string;
    value: any;
    onChange: (val: any) => void;
    className?: string;
    schemaMode?: 'full' | 'inbound' | 'inbounds' | 'outbound' | 'outbounds' | 'rule' | 'dns' | 'balancer' | 'routing';
}

export const JsonField = ({ label, value, onChange, className = "", schemaMode = 'full' }: JsonFieldProps) => {
    const [text, setText] = useState("");
    const [error, setError] = useState(false);

    // Синхронизация внешнего value -> внутренний текст
    useEffect(() => {
        // Убираем технический индекс 'i' перед отображением в JSON
        let displayValue = value;
        if (value && typeof value === 'object' && !Array.isArray(value)) {
            const { i, ...cleanValue } = value as any;
            displayValue = cleanValue;
        }
        
        const newText = JSON.stringify(displayValue, null, 2);
        
        // Сравниваем распарсенные значения, чтобы не затирать текст пользователя, если данные те же
        try {
            const cleanJson = stripComments(text);
            if (text.trim() !== "" && JSON.stringify(JSON.parse(cleanJson)) === JSON.stringify(displayValue)) {
                return;
            }
        } catch (e) {}

        setText(newText);
    }, [value]);

    const stripComments = (jsonString: string) => {
        return jsonString.replace(/("(?:\\.|[^\\"])*")|\/\*[\s\S]*?\*\/|\/\/.*/g, (match, group1) => {
            return group1 ? group1 : "";
        });
    };
const handleEditorChange = (v: string) => {
    setText(v);
    try {
        if (v.trim() === "") {
            // If user clears the field, provide an empty config base instead of undefined
            onChange({ inbounds: [], outbounds: [] });
            setError(false);
        } else {
            const cleanJson = stripComments(v);
            const parsed = JSON.parse(cleanJson);

            // Recursively remove 'i' property and ignore nulls
            const sanitize = (obj: any): any => {
                if (Array.isArray(obj)) return obj.map(sanitize).filter(i => i !== null);
                if (obj && typeof obj === 'object') {
                    const newObj: any = {};
                    for (const key in obj) {
                        if (key === 'i') continue;
                        const val = sanitize(obj[key]);
                        if (val !== null && val !== undefined) newObj[key] = val;
                    }
                    return newObj;
                }
                return obj;
            };

            const sanitized = sanitize(parsed);

            // Reject if resulting object is invalid (e.g. empty or not matching Xray structure)
            if (sanitized && typeof sanitized === 'object') {
                onChange(sanitized);
                setError(false);
            }
        }
    } catch (err) {
        setError(true);
    }
};

    return (
        <div className={`flex flex-col gap-2 h-full w-full min-w-0 ${className}`}>
            {label && (
                <div className="flex justify-between items-end">
                    <label className="text-xs uppercase font-bold text-slate-500">
                        {label}
                    </label>
                    {error && <span className="text-rose-500 font-bold text-[10px] animate-pulse">Invalid JSON Syntax</span>}
                </div>
            )}
            
            <div className={`flex-1 min-h-[65vh] relative rounded-lg overflow-hidden border transition-all bg-[#282c34] ${error ? 'border-rose-500/50' : 'border-slate-700'}`}>
                <div className="absolute inset-0">
                    <JsonEditor 
                        value={text} 
                        onChange={handleEditorChange} 
                        schemaMode={schemaMode} 
                    />
                </div>
            </div>
        </div>
    );
};