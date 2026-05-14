// @ts-nocheck
import { useState, useMemo, useCallback, useEffect, useRef } from 'react';

interface Suggestion {
    code: string;
    count: number;
}

export const useSmartTagInput = (
    value: string[],
    onChange: (val: string[]) => void,
    suggestions: Suggestion[],
    prefix: string,
    cleanRegex: RegExp = /\[\d+\]/g
) => {
    const [input, setInput] = useState("");
    const [showSuggest, setShowSuggest] = useState(false);
    const [focusedIndex, setFocusedIndex] = useState(-1);
    
    const wrapperRef = useRef<HTMLDivElement>(null);
    const suggestionsRef = useRef<HTMLDivElement>(null);

    const filteredSuggestions = useMemo(() => {
        return input && Array.isArray(suggestions)
            ? suggestions
                .filter(s => s?.code?.toLowerCase().includes(input.toLowerCase().replace(prefix, "")))
                .slice(0, 30)
            : [];
    }, [input, suggestions, prefix]);

    const processAndAddTags = useCallback((rawInput: string) => {
        const rawTags = rawInput.split(/[\n,\s]+/);
        let newTags = [...value];
        let added = false;

        rawTags.forEach(rawTag => {
            const cleanTag = rawTag.replace(cleanRegex, '').trim();
            if (cleanTag && !newTags.includes(cleanTag)) {
                newTags.push(cleanTag);
                added = true;
            }
        });

        if (added) {
            onChange(newTags);
        }
        setInput("");
        setShowSuggest(false);
        setFocusedIndex(-1);
    }, [value, onChange, cleanRegex]);

    const removeTag = useCallback((t: string) => onChange(value.filter(v => v !== t)), [value, onChange]);

    return {
        input, setInput,
        showSuggest, setShowSuggest,
        focusedIndex, setFocusedIndex,
        wrapperRef, suggestionsRef,
        filteredSuggestions,
        processAndAddTags,
        removeTag
    };
};
