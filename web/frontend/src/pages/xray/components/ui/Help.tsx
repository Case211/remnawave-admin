import React from 'react';
import { Icon } from './Icon';

interface HelpProps {
    children: React.ReactNode;
}

export const Help = ({ children }: HelpProps) => {
    // We use a native title attribute here because custom CSS tooltips 
    // get clipped by overflow-y-auto containers inside modals.
    // Native tooltips always render on top of everything.
    const text = React.Children.toArray(children).join('').trim();
    
    return (
        <span className="inline-flex items-center ml-1.5 align-middle cursor-help" title={text}>
            <Icon 
                name="Question" 
                className="text-slate-500 hover:text-indigo-400 transition-colors text-[14px]" 
                weight="bold" 
            />
        </span>
    );
};
