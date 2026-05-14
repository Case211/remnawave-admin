import { useState, useMemo, useCallback } from 'react';
import { useConfigStore } from '../store/configStore';
import { getCriticalRuleErrors } from '../utils/validator';
import { createDefaultRoutingRule, createDefaultBalancer } from '../utils/protocol-factories';

export const useRoutingEditor = (onClose: () => void) => {
    const { config, updateSection, reorderRules } = useConfigStore();
    const rules = config?.routing?.rules || [];
    const balancers = config?.routing?.balancers || [];
    
    const outboundTags = useMemo(() => (config?.outbounds || []).map((o: any) => o.tag).filter(Boolean), [config?.outbounds]);
    const inboundTags = useMemo(() => (config?.inbounds || []).map((i: any) => i.tag).filter(Boolean), [config?.inbounds]);
    const balancerTags = useMemo(() => balancers.map((b: any) => b.tag).filter(Boolean), [balancers]);

    const [activeTab, setActiveTab] = useState<'rules' | 'balancers'>('rules');
    const [activeRuleIdx, setActiveRuleIdx] = useState<number | null>(null);
    const [activeBalancerIdx, setActiveBalancerIdx] = useState<number | null>(null);
    const [rawMode, setRawMode] = useState(false);
    const [mobileEditMode, setMobileEditMode] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");

    const brokenRules = useMemo(() => rules
        .map((r: any, i: number) => ({
            idx: i,
            label: r.ruleTag || r.outboundTag || r.balancerTag || `Rule #${i + 1}`,
            errors: getCriticalRuleErrors(r)
        }))
        .filter(r => r.errors.length > 0), [rules]);

    const hasCriticalErrors = brokenRules.length > 0;

    const handleSelectRule = useCallback((originalIdx: number) => {
        setActiveRuleIdx(originalIdx);
        setRawMode(false);
        setMobileEditMode(true);
    }, []);

    const handleClose = useCallback(() => {
        if (hasCriticalErrors) {
            const first = brokenRules[0];
            if (first) {
                setActiveTab('rules');
                handleSelectRule(first.idx);
            }
            return;
        }
        onClose();
    }, [hasCriticalErrors, brokenRules, handleSelectRule, onClose]);

    const filteredRules = useMemo(() => rules
        .map((r: any, originalIndex: number) => ({ ...r, originalIndex }))
        .filter((rule: any) => {
            const q = searchQuery.toLowerCase();
            if (!q) return true;
            return (
                rule.ruleTag?.toLowerCase().includes(q) ||
                rule.outboundTag?.toLowerCase().includes(q) ||
                rule.balancerTag?.toLowerCase().includes(q) ||
                rule.domain?.some((d: string) => d.toLowerCase().includes(q)) ||
                rule.ip?.some((ip: string) => ip.toLowerCase().includes(q)) ||
                rule.inboundTag?.some((t: string) => t.toLowerCase().includes(q)) ||
                rule.protocol?.some((p: string) => p.toLowerCase().includes(q))
            );
        }), [rules, searchQuery]);

    const handleAddRule = useCallback(() => {
        const newRule = createDefaultRoutingRule();
        reorderRules([newRule, ...rules]);
        handleSelectRule(0);
    }, [reorderRules, rules, handleSelectRule]);

    const handleDeleteRule = useCallback((originalIdx: number) => {
        const n = [...rules];
        n.splice(originalIdx, 1);
        reorderRules(n);
        if (activeRuleIdx === originalIdx) {
            setActiveRuleIdx(null);
            setMobileEditMode(false);
        }
    }, [rules, reorderRules, activeRuleIdx]);

    const handleUpdateRule = useCallback((updatedRule: any) => {
        if (activeRuleIdx === null) return;
        const cleanRule = { ...updatedRule };
        delete cleanRule.originalIndex;
        const n = [...rules];
        n[activeRuleIdx] = cleanRule;
        reorderRules(n);
    }, [rules, activeRuleIdx, reorderRules]);

    const handleAddBalancer = useCallback(() => {
        const nb = createDefaultBalancer();
        updateSection('routing', { ...config?.routing, balancers: [...balancers, nb] });
    }, [config?.routing, balancers, updateSection]);

    const handleUpdateBalancer = useCallback((val: any) => {
        if (activeBalancerIdx === null) return;
        const n = [...balancers];
        n[activeBalancerIdx] = val;
        updateSection('routing', { ...config?.routing, balancers: n });
    }, [balancers, activeBalancerIdx, config?.routing, updateSection]);

    const handleDeleteBalancer = useCallback((idx: number) => {
        const n = [...balancers];
        n.splice(idx, 1);
        updateSection('routing', { ...config?.routing, balancers: n });
        if (activeBalancerIdx === idx) {
            setActiveBalancerIdx(null);
            setMobileEditMode(false);
        }
    }, [balancers, activeBalancerIdx, config?.routing, updateSection]);

    return {
        rules,
        balancers,
        outboundTags,
        inboundTags,
        balancerTags,
        activeTab,
        setActiveTab,
        activeRuleIdx,
        activeBalancerIdx,
        setActiveBalancerIdx,
        rawMode,
        setRawMode,
        mobileEditMode,
        setMobileEditMode,
        searchQuery,
        setSearchQuery,
        brokenRules,
        hasCriticalErrors,
        handleClose,
        filteredRules,
        handleSelectRule,
        handleAddRule,
        handleDeleteRule,
        handleUpdateRule,
        handleAddBalancer,
        handleUpdateBalancer,
        handleDeleteBalancer
    };
};
