import { Icon } from '../ui';

interface DragDropOverlayProps {
    visible: boolean;
}

/**
 * Full-screen overlay shown when a file is dragged over the app window.
 */
export const DragDropOverlay = ({ visible }: DragDropOverlayProps) => {
    if (!visible) return null;

    return (
        <div className="absolute inset-0 z-50 bg-indigo-900/80 backdrop-blur-sm border-4 border-indigo-500 border-dashed flex flex-col items-center justify-center pointer-events-none">
            <Icon name="FileArrowDown" className="text-8xl text-indigo-400 mb-4 animate-bounce" weight="fill" />
            <h2 className="text-2xl md:text-3xl font-bold text-white text-center px-4">
                Отпусти config.json здесь
            </h2>
        </div>
    );
};
