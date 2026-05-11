import { useState, useCallback } from 'react';
import { produce } from 'immer';
import type { ValidationError } from '../utils/validator';
import { toast } from 'sonner';

interface UseXrayEditorOptions<T> {
    data: T;
    onSave: (data: T) => void;
    validate: (data: T) => ValidationError[];
    onProtocolChange?: (proto: string) => T;
}

export const useXrayEditor = <T extends Record<string, any>>({
    data,
    onSave,
    validate,
    onProtocolChange
}: UseXrayEditorOptions<T>) => {
    const [local, setLocal] = useState<T>(data);
    const [rawMode, setRawMode] = useState(false);
    const [errors, setErrors] = useState<ValidationError[]>([]);

    const updateField = useCallback((path: string | (string | number)[], value: any) => {
        setLocal(
            produce((draft: any) => {
                if (Array.isArray(path)) {
                    let curr = draft;
                    for (let i = 0; i < path.length - 1; i++) {
                        const key = path[i];
                        if (!curr[key] || typeof curr[key] !== 'object') {
                            curr[key] = typeof path[i+1] === 'number' ? [] : {};
                        }
                        curr = curr[key];
                    }
                    curr[path[path.length - 1]] = value;
                } else {
                    draft[path] = value;
                }
            })
        );
        if (errors.length > 0) setErrors([]);
    }, [errors.length]);

    const handleProtocolChange = useCallback((proto: string) => {
        if (onProtocolChange) {
            setLocal(onProtocolChange(proto));
        } else {
            updateField('protocol', proto);
        }
        setErrors([]);
    }, [onProtocolChange, updateField]);

    const handleSave = useCallback(() => {
        const validationErrors = validate(local);
        if (validationErrors.length > 0) {
            setErrors(validationErrors);
            toast.error("Please fix validation errors before saving");
            return;
        }
        onSave(local);
    }, [local, onSave, validate]);

    const getError = useCallback((field: string) => 
        errors.find(e => e.field === field)?.message
    , [errors]);

    return {
        local,
        setLocal,
        updateField,
        handleProtocolChange,
        handleSave,
        rawMode,
        setRawMode,
        errors,
        setErrors,
        getError
    };
};
