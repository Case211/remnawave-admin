import React from 'react';
import { Button as ShadButton } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Icon } from './Icon';

export type ButtonVariant = 'primary' | 'success' | 'danger' | 'secondary' | 'ghost' | 'warning';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: ButtonVariant;
    size?: ButtonSize;
    icon?: string;
    iconWeight?: 'regular' | 'bold' | 'fill' | 'duotone';
    loading?: boolean;
    children?: React.ReactNode;
}

/**
 * Adapter: preserves the upstream xray-editor Button API (variant/size/icon/loading),
 * renders our shadcn Button underneath. Success/warning don't exist in shadcn —
 * map them via override classNames so call sites don't have to change.
 */
const variantMap: Record<ButtonVariant, 'default' | 'destructive' | 'secondary' | 'ghost'> = {
    primary: 'default',
    success: 'default',
    danger: 'destructive',
    warning: 'default',
    secondary: 'secondary',
    ghost: 'ghost',
};

const sizeMap: Record<ButtonSize, 'sm' | 'default' | 'lg'> = {
    sm: 'sm',
    md: 'default',
    lg: 'lg',
};

const variantOverrides: Partial<Record<ButtonVariant, string>> = {
    success:
        'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-500/20 ring-1 ring-white/10',
    warning: 'bg-amber-500 hover:bg-amber-400 text-black shadow-lg shadow-amber-500/10',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    (
        {
            variant = 'primary',
            size = 'md',
            icon,
            iconWeight = 'regular',
            loading = false,
            children,
            className = '',
            disabled,
            ...rest
        },
        ref,
    ) => {
        return (
            <ShadButton
                ref={ref}
                variant={variantMap[variant]}
                size={sizeMap[size]}
                disabled={disabled || loading}
                className={cn(
                    'gap-2',
                    variantOverrides[variant],
                    className,
                )}
                {...rest}
            >
                {loading ? (
                    <Icon name="CircleNotch" className="animate-spin" />
                ) : (
                    icon && <Icon name={icon} weight={iconWeight} />
                )}
                {children}
            </ShadButton>
        );
    },
);

Button.displayName = 'Button';
