import React from 'react';
import {
    Card as ShadCard,
    CardHeader as ShadCardHeader,
    CardContent as ShadCardContent,
} from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { Icon } from './Icon';

interface CardProps {
    title?: string;
    icon?: string;
    children: React.ReactNode;
    className?: string;
    headerExtra?: React.ReactNode;
}

/**
 * Adapter: keeps the upstream xray-editor Card API (title/icon/headerExtra/children)
 * but renders through the admin panel's shadcn Card (glass-card). The upstream
 * built a header internally; we compose with shadcn's CardHeader + a custom
 * row for icon/title/headerExtra to keep the visual rhythm.
 */
export const Card = ({
    title,
    icon,
    children,
    className = '',
    headerExtra,
}: CardProps) => {
    const hasHeader = !!(title || icon || headerExtra);

    return (
        <ShadCard className={cn('overflow-hidden', className)}>
            {hasHeader && (
                <ShadCardHeader className="pb-3 pt-4 px-4 md:px-6 flex-row justify-between items-center space-y-0">
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2 m-0">
                        {icon && <Icon name={icon} className="text-indigo-400" />}
                        {title}
                    </h4>
                    {headerExtra}
                </ShadCardHeader>
            )}
            <ShadCardContent className={cn('space-y-4 px-4 md:px-6', hasHeader ? 'pb-4' : 'py-4')}>
                {children}
            </ShadCardContent>
        </ShadCard>
    );
};
