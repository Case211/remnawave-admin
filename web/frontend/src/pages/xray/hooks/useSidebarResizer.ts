import { useState, useCallback, useEffect } from 'react';

export const useSidebarResizer = (initialWidth: number = 380, min: number = 250, max: number = 800) => {
    const [sidebarWidth, setSidebarWidth] = useState(initialWidth);
    const [isResizing, setIsResizing] = useState(false);

    const startResizing = useCallback(() => setIsResizing(true), []);
    const stopResizing = useCallback(() => setIsResizing(false), []);

    const resize = useCallback((e: MouseEvent) => {
        if (isResizing) {
            setSidebarWidth(prev => Math.min(max, Math.max(min, prev + e.movementX)));
        }
    }, [isResizing, min, max]);

    useEffect(() => {
        if (isResizing) {
            window.addEventListener("mousemove", resize);
            window.addEventListener("mouseup", stopResizing);
            document.body.style.cursor = "col-resize";
        } else {
            document.body.style.cursor = "default";
        }
        return () => {
            window.removeEventListener("mousemove", resize);
            window.removeEventListener("mouseup", stopResizing);
        };
    }, [isResizing, resize, stopResizing]);

    return { sidebarWidth, isResizing, startResizing };
};
