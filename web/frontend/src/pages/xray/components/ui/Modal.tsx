// @ts-nocheck
import React from 'react';
import { Button } from './Button';
import { Icon } from './Icon';

export const Modal = ({ title, onClose, onSave, children, extraButtons = null, className = "", isSecondary = false }) => {
  const [isFullScreen, setIsFullScreen] = React.useState(false);

  React.useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center ${isSecondary ? 'bg-black/40' : 'bg-black/80 backdrop-blur-sm'} animate-in fade-in duration-200 ${isFullScreen ? 'p-0 is-modal-fullscreen' : 'p-2 md:p-4'}`}>
      <div className={`bg-slate-900 border border-slate-700 w-full flex flex-col shadow-2xl animate-in zoom-in-95 duration-200 
        ${isFullScreen ? 'h-full md:rounded-none' : 'h-full md:h-auto md:max-h-[90vh] md:rounded-2xl'} 
        ${isFullScreen ? 'max-w-full' : (className.includes('max-w-') ? '' : 'max-w-[95vw] xl:max-w-[75vw] 2xl:max-w-[1400px]')} ${className}`}>
        
        {/* Header */}
        <div className="flex justify-between items-center p-4 md:p-5 border-b border-slate-800 shrink-0">
          <div className="flex items-center gap-3 min-w-0 relative z-10">
            <h3 className="text-lg md:text-xl font-bold text-white flex items-center gap-2 truncate">
                <Icon name="PencilSimple" className="text-indigo-400 shrink-0"/> {title}
            </h3>
            <button
              onClick={() => setIsFullScreen(!isFullScreen)}
              title={isFullScreen ? "Выйти из полноэкранного режима" : "На весь экран"}
              className="text-slate-500 hover:text-indigo-400 p-1.5 hover:bg-slate-800 rounded-lg transition-all hidden md:block"
            >
              <Icon name={isFullScreen ? "CornersIn" : "CornersOut"} className="text-base" />
            </button>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-2 hover:bg-slate-800 rounded-lg transition-colors shrink-0 relative z-10">
              <Icon name="X" className="text-xl" />
          </button>
        </div>

        {/* Content */}
        <div className={`${isFullScreen ? 'p-1' : 'p-4 md:p-6'} ${className.includes('overflow-hidden') ? 'overflow-hidden' : 'overflow-y-auto'} custom-scroll flex-1 relative flex flex-col min-h-0`}>
          {children}
        </div>

        {/* Footer */}
        <div className="p-4 md:p-5 border-t border-slate-800 flex flex-col-reverse md:flex-row justify-between items-center bg-slate-900 md:rounded-b-2xl shrink-0 gap-3 md:gap-0 z-20">
          <div className="flex gap-2 w-full md:w-auto overflow-x-auto pb-1 md:pb-0 hide-scrollbar relative z-10">
              {extraButtons}
          </div>
          <div className="flex gap-3 w-full md:w-auto relative z-10">
              <Button variant="secondary" onClick={onClose} className="flex-1 md:flex-none">Закрыть</Button>
              {onSave !== onClose && <Button variant="success" onClick={onSave} icon="FloppyDisk" className="flex-1 md:flex-none">Сохранить</Button>}
          </div>
        </div>
      </div>
    </div>
  );
};
