// @ts-nocheck
import React from 'react';
import { InboundModal } from '../editors/InboundModal';
import { OutboundModal } from '../editors/OutboundModal';
import { RoutingModal } from '../editors/RoutingModal';
import { DnsModal } from '../editors/DnsModal';
import { SettingsModal } from '../editors/SettingsModal';
import { ReverseModal } from '../editors/ReverseModal';
import { TopologyModal } from '../topology/TopologyModal';
import { RemnawaveModal } from '../editors/RemnawaveModal';
import { SectionJsonModal } from '../editors/SectionJsonModal';
import { BatchOutboundModal } from '../editors/outbound/BatchOutboundModal';
import { GeoViewerModal } from '../editors/GeoViewerModal';
import { DiagnosticsPanel } from '../DiagnosticsPanel';
import { AboutModal } from '../AboutModal';
import { WarpGeneratorModal } from '../editors/WarpGeneratorModal';
import { ConfigInspectorModal } from '../editors/ConfigInspectorModal';
import type { Diagnostic } from '../../core/diagnostics';

export interface ModalState {
    type: string | null;
    data: any;
    index: number | null;
}

export interface SectionModalState {
    open: boolean;
    title: string;
    section: string;
    data: any;
    schemaMode: any;
}

interface ModalManagerProps {
    modal: ModalState;
    onCloseModal: () => void;
    onSaveModal: (data: any) => void;

    sectionModal: SectionModalState;
    onCloseSectionModal: () => void;
    onSaveSection: (data: any) => void;

    remnawaveModalOpen: boolean;
    onCloseRemnawave: () => void;

    batchModalOpen: boolean;
    onCloseBatch: () => void;

    geoViewerOpen: boolean;
    onCloseGeoViewer: () => void;

    diagnosticsOpen: boolean;
    onCloseDiagnostics: () => void;
    diagnostics: Diagnostic[];

    warpModalOpen: boolean;
    onCloseWarpModal: () => void;
    onGenerateWarp: (outbound: any) => void;

    aboutOpen: boolean;
    onCloseAbout: () => void;

    configInspectorOpen: boolean;
    onCloseConfigInspector: () => void;
    setModal: (m: any) => void;
    openSectionJson: (section: string, title: string, data: any) => void;
}

/**
 * Centralised modal renderer.
 * Keeps App.tsx clean — just pass modal states and handlers here.
 */
export const ModalManager = ({
    modal,
    onCloseModal,
    onSaveModal,
    sectionModal,
    onCloseSectionModal,
    onSaveSection,
    remnawaveModalOpen,
    onCloseRemnawave,
    batchModalOpen,
    onCloseBatch,
    geoViewerOpen,
    onCloseGeoViewer,
    diagnosticsOpen,
    onCloseDiagnostics,
    diagnostics,
    warpModalOpen,
    onCloseWarpModal,
    onGenerateWarp,
    aboutOpen,
    onCloseAbout,
    configInspectorOpen,
    onCloseConfigInspector,
    setModal,
    openSectionJson,
}: ModalManagerProps) => (
    <>
        {configInspectorOpen && <ConfigInspectorModal onClose={onCloseConfigInspector} setModal={setModal} openSectionJson={openSectionJson} />}
        
        {modal.type === 'inbound' && (
            <InboundModal data={modal.data} onClose={onCloseModal} onSave={onSaveModal} />
        )}
        {modal.type === 'outbound' && (
            <OutboundModal data={modal.data} onClose={onCloseModal} index={modal.index} onSave={onSaveModal} />
        )}
        {modal.type === 'routing' && <RoutingModal onClose={onCloseModal} />}
        {modal.type === 'dns' && <DnsModal onClose={onCloseModal} />}
        {modal.type === 'settings' && <SettingsModal onClose={onCloseModal} />}
        {modal.type === 'reverse' && <ReverseModal onClose={onCloseModal} />}
        {modal.type === 'topology' && <TopologyModal onClose={onCloseModal} />}

        {batchModalOpen && <BatchOutboundModal onClose={onCloseBatch} />}
        {geoViewerOpen && <GeoViewerModal onClose={onCloseGeoViewer} />}
        {warpModalOpen && <WarpGeneratorModal onClose={onCloseWarpModal} onGenerate={onGenerateWarp} />}

        {sectionModal.open && (
            <SectionJsonModal
                title={sectionModal.title}
                data={sectionModal.data}
                schemaMode={sectionModal.schemaMode}
                onClose={onCloseSectionModal}
                onSave={onSaveSection}
            />
        )}
        {remnawaveModalOpen && <RemnawaveModal onClose={onCloseRemnawave} />}
        {aboutOpen && <AboutModal onClose={onCloseAbout} />}
        {diagnosticsOpen && (
            <DiagnosticsPanel diagnostics={diagnostics} onClose={onCloseDiagnostics} />
        )}
    </>
);
