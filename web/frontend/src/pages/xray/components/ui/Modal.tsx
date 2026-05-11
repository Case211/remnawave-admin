import React from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { Button as ShadButton } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Button } from './Button';
import { Icon } from './Icon';

/**
 * Compatibility wrapper that preserves the upstream xray-editor's Modal API
 * but renders through Radix Dialog primitives directly so we control the
 * overlay opacity (isSecondary) and outside-click behaviour.
 *
 * Upstream Modal closed only on ESC or the X button — clicks on the backdrop
 * did NOT close the dialog (because the upstream rendered the backdrop as a
 * plain div without a click handler). We mirror that here by preventing
 * Radix's onInteractOutside / onPointerDownOutside.
 *
 * On mobile (≤768px) we additionally support swipe-down-to-dismiss anchored
 * on the title bar: drag the header down ≥80px and the modal closes. The
 * gesture is ignored on desktop and when started with a mouse pointer.
 *
 * isSecondary toggles the overlay opacity (bg-black/40 vs bg-black/80) so
 * stacked dialogs — e.g. TagDetailsModal opened over the main editor —
 * stay visually distinguishable.
 *
 * The fullscreen toggle lives in the title bar; Radix doesn't ship one.
 */
interface ModalProps {
    title: React.ReactNode;
    onClose: () => void;
    onSave?: () => void;
    children: React.ReactNode;
    extraButtons?: React.ReactNode;
    className?: string;
    isSecondary?: boolean;
}

const DISMISS_THRESHOLD_PX = 80;

export const Modal = ({
    title,
    onClose,
    onSave,
    children,
    extraButtons = null,
    className = '',
    isSecondary = false,
}: ModalProps) => {
    const [isFullScreen, setIsFullScreen] = React.useState(false);
    const [dragY, setDragY] = React.useState(0);
    const dragStateRef = React.useRef<{ startY: number; pointerId: number } | null>(null);

    const isTouchPointer = (e: React.PointerEvent<HTMLDivElement>) =>
        e.pointerType === 'touch' && window.matchMedia('(max-width: 767px)').matches;

    const handleHeaderPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
        if (!isTouchPointer(e)) return;
        // Don't hijack pointer events that started on actual buttons (X, fullscreen).
        if ((e.target as HTMLElement).closest('button')) return;
        dragStateRef.current = { startY: e.clientY, pointerId: e.pointerId };
        (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
    };

    const handleHeaderPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
        const state = dragStateRef.current;
        if (!state || state.pointerId !== e.pointerId) return;
        const dy = Math.max(0, e.clientY - state.startY); // only downward
        setDragY(dy);
    };

    const handleHeaderPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
        const state = dragStateRef.current;
        if (!state || state.pointerId !== e.pointerId) return;
        const dy = e.clientY - state.startY;
        dragStateRef.current = null;
        try {
            (e.currentTarget as HTMLDivElement).releasePointerCapture(e.pointerId);
        } catch {
            /* pointer already released by the browser — fine */
        }
        if (dy >= DISMISS_THRESHOLD_PX) {
            onClose();
        }
        setDragY(0);
    };

    return (
        <DialogPrimitive.Root open onOpenChange={(v) => { if (!v) onClose(); }}>
            <DialogPrimitive.Portal>
                <DialogPrimitive.Overlay
                    className={cn(
                        'fixed inset-0 z-50 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
                        isSecondary ? 'bg-black/40' : 'bg-black/80',
                    )}
                    style={dragY > 0 ? { opacity: Math.max(0.3, 1 - dragY / 400) } : undefined}
                />
                <DialogPrimitive.Content
                    onEscapeKeyDown={(e) => { e.preventDefault(); onClose(); }}
                    onInteractOutside={(e) => e.preventDefault()}
                    onPointerDownOutside={(e) => e.preventDefault()}
                    className={cn(
                        'fixed z-50 flex flex-col gap-0 bg-slate-900 border border-slate-700 shadow-2xl p-0',
                        'duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
                        'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
                        'left-[50%] top-[50%] translate-x-[-50%] translate-y-[-50%]',
                        'w-full max-w-[95vw] xl:max-w-[75vw] 2xl:max-w-[1400px]',
                        'h-full md:h-auto md:max-h-[90vh] md:rounded-2xl',
                        isSecondary && 'bg-slate-900/95',
                        isFullScreen && 'h-full md:h-screen md:max-h-screen md:max-w-full md:w-full md:rounded-none is-modal-fullscreen',
                        className,
                    )}
                    style={
                        dragY > 0
                            ? { transform: `translate(-50%, calc(-50% + ${dragY}px))`, transition: 'none' }
                            : undefined
                    }
                >
                    {/* Header — doubles as a drag-handle on mobile */}
                    <div
                        className="flex justify-between items-center p-4 md:p-5 border-b border-slate-800 shrink-0 touch-none md:touch-auto select-none md:select-auto cursor-grab md:cursor-default"
                        onPointerDown={handleHeaderPointerDown}
                        onPointerMove={handleHeaderPointerMove}
                        onPointerUp={handleHeaderPointerUp}
                        onPointerCancel={handleHeaderPointerUp}
                    >
                        {/* Visual grab handle (mobile only) */}
                        <span
                            aria-hidden="true"
                            className="md:hidden absolute top-1.5 left-1/2 -translate-x-1/2 h-1 w-10 rounded-full bg-slate-700"
                        />
                        <div className="flex items-center gap-3 min-w-0 relative z-10">
                            <DialogPrimitive.Title className="text-lg md:text-xl font-bold text-white flex items-center gap-2 truncate">
                                <Icon name="PencilSimple" className="text-indigo-400 shrink-0" /> {title}
                            </DialogPrimitive.Title>
                            <button
                                type="button"
                                onClick={() => setIsFullScreen(!isFullScreen)}
                                title={isFullScreen ? 'Выйти из полноэкранного режима' : 'На весь экран'}
                                className="text-slate-500 hover:text-indigo-400 p-1.5 hover:bg-slate-800 rounded-lg transition-all hidden md:block"
                            >
                                <Icon name={isFullScreen ? 'CornersIn' : 'CornersOut'} className="text-base" />
                            </button>
                        </div>
                        <DialogPrimitive.Close asChild>
                            <button
                                type="button"
                                onClick={onClose}
                                className="text-slate-400 hover:text-white p-2 hover:bg-slate-800 rounded-lg transition-colors shrink-0 relative z-10 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 flex items-center justify-center"
                                aria-label="Закрыть"
                            >
                                <Icon name="X" className="text-xl" />
                            </button>
                        </DialogPrimitive.Close>
                    </div>

                    {/* Content */}
                    <div
                        className={cn(
                            'flex-1 relative flex flex-col min-h-0 custom-scroll',
                            isFullScreen ? 'p-1' : 'p-4 md:p-6',
                            className?.includes?.('overflow-hidden') ? 'overflow-hidden' : 'overflow-y-auto',
                        )}
                    >
                        {children}
                    </div>

                    {/* Footer */}
                    <div className="p-4 md:p-5 border-t border-slate-800 flex flex-col-reverse md:flex-row md:justify-between items-center bg-slate-900 md:rounded-b-2xl shrink-0 gap-3 md:gap-0 z-20">
                        <div className="flex gap-2 w-full md:w-auto overflow-x-auto pb-1 md:pb-0 hide-scrollbar relative z-10">
                            {extraButtons}
                        </div>
                        <div className="flex gap-3 w-full md:w-auto relative z-10">
                            <ShadButton variant="secondary" onClick={onClose} className="flex-1 md:flex-none">
                                Закрыть
                            </ShadButton>
                            {onSave && onSave !== onClose && (
                                <Button variant="success" onClick={onSave} icon="FloppyDisk" className="flex-1 md:flex-none">
                                    Сохранить
                                </Button>
                            )}
                        </div>
                    </div>
                </DialogPrimitive.Content>
            </DialogPrimitive.Portal>
        </DialogPrimitive.Root>
    );
};
