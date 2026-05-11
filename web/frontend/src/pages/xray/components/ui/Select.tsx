// @ts-nocheck
import React, { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from './Icon';

export interface SelectOption<T extends string = string> {
    value: T;
    label: string;
    description?: string;
    disabled?: boolean;
}

export interface SelectProps<T extends string = string> {
    value: T;
    onChange: (value: T) => void;
    options: SelectOption<T>[];
    label?: string;
    error?: string;
    hint?: string;
    placeholder?: string;
    disabled?: boolean;
    className?: string;
    id?: string;
}

/**
 * Custom dropdown.
 *
 * The options list is rendered through `createPortal(document.body)` so it
 * escapes any `overflow:hidden` ancestor (Modal content, RuleEditor scrollable
 * area, SmartTagInput suggestions, etc). Without the portal the list got
 * clipped by the first overflow-clipping parent and users couldn't read or
 * select the items below the fold.
 *
 * Positioning is updated on open + on window resize/scroll via
 * `getBoundingClientRect()` of the trigger button. The popup flips above the
 * trigger if there isn't enough room below.
 */
export function Select<T extends string = string>({
    value,
    onChange,
    options,
    label,
    error,
    hint,
    placeholder = "Select option...",
    disabled = false,
    className = '',
    id,
}: SelectProps<T>) {
    const [isOpen, setIsOpen] = useState(false);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const popperRef = useRef<HTMLDivElement>(null);
    const [popperStyle, setPopperStyle] = useState<React.CSSProperties>({});

    const selectedOption = options.find(opt => opt.value === value);
    const selectId = id ?? label?.toLowerCase().replace(/\s+/g, '-');

    const computePosition = () => {
        const trigger = triggerRef.current;
        if (!trigger) return;
        const rect = trigger.getBoundingClientRect();
        const POPPER_MAX_H = 260; // matches max-h below + small breathing room
        const GAP = 6;
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;
        const placeAbove = spaceBelow < POPPER_MAX_H && spaceAbove > spaceBelow;

        setPopperStyle({
            position: 'fixed',
            left: rect.left,
            width: rect.width,
            ...(placeAbove
                ? { top: Math.max(8, rect.top - POPPER_MAX_H - GAP) }
                : { top: rect.bottom + GAP }),
            maxHeight: POPPER_MAX_H,
            zIndex: 9999,
            // Radix Dialog (modal=true) sets pointer-events: none on body so
            // clicks outside its Content get swallowed. Our popper lives on
            // body via createPortal — explicitly re-enable pointer events on it.
            pointerEvents: 'auto',
        });
    };

    useLayoutEffect(() => {
        if (!isOpen) return;
        computePosition();
        const handler = () => computePosition();
        window.addEventListener('resize', handler);
        window.addEventListener('scroll', handler, true); // capture all scroll containers
        return () => {
            window.removeEventListener('resize', handler);
            window.removeEventListener('scroll', handler, true);
        };
    }, [isOpen]);

    useEffect(() => {
        if (!isOpen) return;
        const handleClickOutside = (event: MouseEvent) => {
            const t = event.target as Node;
            if (triggerRef.current?.contains(t)) return;
            if (popperRef.current?.contains(t)) return;
            setIsOpen(false);
        };
        const handleKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setIsOpen(false);
        };
        document.addEventListener('mousedown', handleClickOutside);
        document.addEventListener('keydown', handleKey);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
            document.removeEventListener('keydown', handleKey);
        };
    }, [isOpen]);

    const handleSelect = (val: T) => {
        onChange(val);
        setIsOpen(false);
    };

    const border = error
        ? 'border-rose-500/70'
        : isOpen ? 'border-indigo-500 ring-1 ring-indigo-500/20' : 'border-slate-700';

    return (
        <div className={`flex flex-col gap-1.5 ${className}`}>
            {label && (
                <label htmlFor={selectId} className="text-[10px] uppercase text-slate-500 font-bold tracking-widest">
                    {label}
                </label>
            )}

            <div className="relative">
                <button
                    ref={triggerRef}
                    id={selectId}
                    type="button"
                    onClick={() => !disabled && setIsOpen(!isOpen)}
                    disabled={disabled}
                    aria-haspopup="listbox"
                    aria-expanded={isOpen}
                    className={`
                        w-full bg-slate-950 border rounded-lg h-11
                        text-white px-4 text-sm flex items-center justify-between
                        transition-all duration-200 text-left
                        disabled:opacity-50 disabled:cursor-not-allowed
                        ${border}
                    `}
                >
                    <span className={!selectedOption ? 'text-slate-500' : 'text-white'}>
                        {selectedOption ? selectedOption.label : placeholder}
                    </span>
                    <Icon
                        name="CaretDown"
                        weight="bold"
                        className={`text-slate-500 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
                    />
                </button>

                {isOpen && createPortal(
                    <div
                        ref={popperRef}
                        role="listbox"
                        style={popperStyle}
                        className="bg-[#0f172a] border border-slate-700 rounded-xl shadow-[0_20px_50px_rgba(0,0,0,0.6)] overflow-hidden ring-1 ring-white/10 animate-in fade-in zoom-in-95 duration-150"
                    >
                        <div className="overflow-y-auto custom-scroll p-1.5 space-y-0.5 bg-[#0f172a]" style={{ maxHeight: popperStyle.maxHeight }}>
                            {options.length === 0 ? (
                                <div className="p-3 text-xs text-slate-600 text-center italic">Нет вариантов</div>
                            ) : (
                                options.map((opt) => {
                                    const isActive = opt.value === value;
                                    return (
                                        <button
                                            key={opt.value}
                                            type="button"
                                            role="option"
                                            aria-selected={isActive}
                                            onClick={() => !opt.disabled && handleSelect(opt.value)}
                                            disabled={opt.disabled}
                                            className={`
                                                w-full text-left px-3 py-2 rounded-lg transition-all duration-200
                                                ${isActive
                                                    ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20 ring-1 ring-indigo-400/30'
                                                    : 'text-slate-300 hover:bg-white/5 hover:text-white'}
                                                ${opt.disabled ? 'opacity-30 cursor-not-allowed' : ''}
                                            `}
                                        >
                                            <div className="flex items-center justify-between">
                                                <span className="font-bold text-xs">{opt.label}</span>
                                                {isActive && <Icon name="Check" weight="bold" className="text-[10px]" />}
                                            </div>
                                            {opt.description && (
                                                <div className={`text-[10px] mt-0.5 leading-tight ${isActive ? 'text-indigo-100/70' : 'text-slate-500'}`}>
                                                    {opt.description}
                                                </div>
                                            )}
                                        </button>
                                    );
                                })
                            )}
                        </div>
                    </div>,
                    document.body,
                )}
            </div>

            {error && (
                <span className="text-[10px] text-rose-500 font-bold animate-in fade-in">
                    {error}
                </span>
            )}
            {hint && !error && <span className="text-[10px] text-slate-600">{hint}</span>}
        </div>
    );
}
