// @ts-nocheck
import React from 'react';
import * as PhosphorIcons from '@phosphor-icons/react';
import { clsx } from 'clsx';

export const Icon = ({ name, className = "", weight = "regular" }: { name: string, className?: string, weight?: any }) => {
    // Преобразуем kebab-case в PascalCase (pencil-simple -> PencilSimple)
    // И обрабатываем случай, если имя уже в PascalCase
    const componentName = name.includes('-') 
        ? name.split('-').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join('')
        : name.charAt(0).toUpperCase() + name.slice(1);
    
    // @ts-ignore
    const IconComponent = PhosphorIcons[componentName];

    if (!IconComponent) {
        // Fallback если иконка не найдена
        return <span className={clsx("text-red-500 font-bold text-xs", className)}>?</span>;
    }

    return <IconComponent weight={weight} className={clsx("inline-block shrink-0", className)} />;
};
