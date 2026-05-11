import { useState, useCallback } from 'react';
import { useConfigStore } from '../store/configStore';

export const useReverseEditor = () => {
    const { config, updateSection } = useConfigStore();
    const reverse = config?.reverse || { bridges: [], portals: [] };
    const [activeTab, setActiveTab] = useState<'bridges' | 'portals'>('bridges');

    const updateList = useCallback((type: 'bridges' | 'portals', newList: any[]) => {
        updateSection('reverse', { ...reverse, [type]: newList });
    }, [reverse, updateSection]);

    const addItem = useCallback((type: 'bridges' | 'portals') => {
        updateList(type, [...(reverse[type] || []), { tag: "reverse-" + type, domain: "example.com" }]);
    }, [reverse, updateList]);

    const removeItem = useCallback((type: 'bridges' | 'portals', idx: number) => {
        const n = [...(reverse[type] || [])];
        n.splice(idx, 1);
        updateList(type, n);
    }, [reverse, updateList]);

    const updateItem = useCallback((type: 'bridges' | 'portals', idx: number, field: string, val: string) => {
        const n = [...(reverse[type] || [])];
        n[idx] = { ...n[idx], [field]: val };
        updateList(type, n);
    }, [reverse, updateList]);

    return {
        reverse,
        activeTab,
        setActiveTab,
        addItem,
        removeItem,
        updateItem
    };
};
