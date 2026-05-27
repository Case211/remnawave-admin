// @ts-nocheck
import React from 'react';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { DnsServerEditor } from './DnsServerEditor';
import { useConfigStore } from '../../../store/configStore'; // Если нужно обновлять глобально, но тут мы принимаем пропсы

// DnD Imports
import { DndContext, closestCenter } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

// Компонент одного элемента (Sortable)
const SortableDnsItem = ({ server, id, isActive, onClick, onDelete }) => {
    const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id });
    const style = { transform: CSS.Transform.toString(transform), transition, zIndex: transform ? 999 : 'auto' };

    const isString = typeof server === 'string';
    const address = isString ? server : server.address;
    const domains = !isString && server.domains ? server.domains.length : 0;

    return (
        <div ref={setNodeRef} style={style} {...attributes}
            onClick={onClick}
            className={`bg-slate-900 border p-3 rounded-lg flex justify-between items-center group cursor-pointer transition-all select-none
                ${isActive ? 'border-indigo-500 bg-indigo-900/20' : 'border-slate-800 hover:border-slate-600'}
            `}
        >
            <div className="flex items-center gap-3 overflow-hidden">
                {/* Drag Handle */}
                <div {...listeners} className="cursor-grab text-slate-600 hover:text-slate-300 p-1 touch-none">
                    <Icon name="DotsSixVertical" />
                </div>

                <div className={`p-2 rounded shrink-0 ${isString ? 'bg-slate-800 text-slate-400' : 'bg-indigo-900/30 text-indigo-400'}`}>
                    <Icon name={isString ? "GlobeSimple" : "SlidersHorizontal"} />
                </div>
                
                <div className="min-w-0">
                    <div className="text-sm font-mono font-bold text-slate-200 truncate">{address}</div>
                    {!isString && (
                        <div className="text-[10px] text-slate-500 flex gap-2">
                            {domains > 0 && <span className="bg-slate-800 px-1 rounded text-slate-400 whitespace-nowrap">{domains} domains</span>}
                            {server.skipFallback && <span className="text-orange-400 whitespace-nowrap">Skip Fallback</span>}
                        </div>
                    )}
                </div>
            </div>
            
            <button onClick={(e) => { e.stopPropagation(); onDelete(); }} className="md:opacity-0 md:group-hover:opacity-100 p-2 hover:text-rose-500 transition-opacity">
                <Icon name="Trash" />
            </button>
        </div>
    );
};

export const DnsServers = ({ servers = [], onSelect, onAdd, onDelete, onReorder }) => {
    
    const handleDragEnd = (event) => {
        const { active, over } = event;
        if (!over || active.id === over.id) return;

        const oldIndex = parseInt(active.id.split('-')[1]);
        const newIndex = parseInt(over.id.split('-')[1]);
        
        const newServers = [...servers];
        const [moved] = newServers.splice(oldIndex, 1);
        newServers.splice(newIndex, 0, moved);
        
        onReorder(newServers);
    };

    return (
        <div className="space-y-4 h-full flex flex-col">
            <div className="flex justify-between items-center">
                <label className="label-xs">DNS Servers Priority List</label>
                <div className="flex gap-2">
                    <Button variant="secondary" size="sm" onClick={() => onAdd("8.8.8.8")} icon="Plus">Simple</Button>
                    <Button variant="primary" size="sm" onClick={() => onAdd({ address: "https://1.1.1.1/dns-query", domains: [] })} icon="Plus">Advanced</Button>
                </div>
            </div>
            
            <div className="flex-1 overflow-y-auto custom-scroll space-y-2 pr-1">
                <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                    <SortableContext items={servers.map((_, i) => `srv-${i}`)} strategy={verticalListSortingStrategy}>
                        {servers.map((s, i) => (
                            <SortableDnsItem 
                                key={`srv-${i}`} 
                                id={`srv-${i}`} 
                                server={s} 
                                isActive={false} // Можно добавить состояние активного выбора
                                onClick={() => onSelect(i)}
                                onDelete={() => onDelete(i)}
                            />
                        ))}
                    </SortableContext>
                </DndContext>
                
                {servers.length === 0 && <div className="text-center text-slate-600 text-xs py-8">No DNS servers defined.</div>}
            </div>
        </div>
    );
};