import React from 'react';
import { Toaster } from 'sonner';
import { useNavigate, useSearchParams } from 'react-router-dom';
import './xray-editor.css';
import { useAppLogic } from './hooks/useAppLogic';
import { getPresets } from './core/presets';
import { useConfigStore } from './store/configStore';
import {
    AppNav,
    WelcomeScreen,
    ConfigDashboard,
    DragDropOverlay,
    ModalManager,
} from './components/layout';

export default function XrayEditor() {
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const [modulesVisible, setModulesVisible] = React.useState(false);

    // Deep-link: /resources/xray?profile=<uuid> открывает конкретный профиль
    // (кнопка «Открыть в редакторе» на витрине профилей в Resources).
    const requestedProfile = searchParams.get('profile');

    // Auto-connect through the admin's JWT (no login form needed) and, if
    // exactly one config-profile exists in the Panel, pre-load it so the
    // user lands on the editor instead of WelcomeScreen.
    const autoConnect = useConfigStore((s: any) => s.autoConnectAdminSession);
    const fetchProfiles = useConfigStore((s: any) => s.fetchRemnawaveProfiles);
    const loadProfile = useConfigStore((s: any) => s.loadRemnawaveProfile);
    const activeProfileUuid = useConfigStore((s: any) => s.remnawave.activeProfileUuid);

    React.useEffect(() => {
        let cancelled = false;
        autoConnect();
        (async () => {
            try {
                if (requestedProfile) {
                    // Явный запрос профиля через URL имеет приоритет над
                    // автовыбором. Параметр одноразовый: убираем его после
                    // обработки, иначе effect перезатрёт ручную смену
                    // профиля внутри редактора.
                    if (activeProfileUuid !== requestedProfile) {
                        await loadProfile(requestedProfile);
                    }
                    if (!cancelled) {
                        setSearchParams({}, { replace: true });
                    }
                    return;
                }
                const profiles = await fetchProfiles();
                if (cancelled || !Array.isArray(profiles) || profiles.length === 0) return;
                if (activeProfileUuid) return;
                if (profiles.length === 1) {
                    await loadProfile(profiles[0].uuid);
                }
            } catch {
                // Network/RBAC issue — WelcomeScreen still renders.
            }
        })();
        return () => { cancelled = true; };
    }, [autoConnect, fetchProfiles, loadProfile, activeProfileUuid, requestedProfile, setSearchParams]);
    const {
        config, setConfig, deleteItem, addItem, remnawave, disconnectRemnawave, initDns,
        modal, setModal,
        sectionModal, setSectionModal,
        remnawaveModalOpen, setRemnawaveModalOpen,
        batchModalOpen, setBatchModalOpen,
        geoViewerOpen, setGeoViewerOpen,
        diagnosticsOpen, setDiagnosticsOpen,
        aboutOpen, setAboutOpen,
        warpModalOpen, setWarpModalOpen,
        configInspectorOpen, setConfigInspectorOpen,
        rawMode, setRawMode,
        isDragging,
        obSearch, setObSearch,
        pushStage, setPushStage,
        handleRealPush,
        handleFileUpload,
        downloadConfig,
        handleDragOver,
        handleDragLeave,
        handleDrop,
        handleSaveModal,
        handleSaveSection,
        openSectionJson,
        diagnostics,
        criticalCount,
        warningCount,
        filteredOutbounds,
        moveItem,
    } = useAppLogic();

    const closeModal = () => setModal({ type: null, data: null, index: null });

    return (
        <div
            className="xray-page h-dvh flex flex-col bg-background text-foreground font-sans selection:bg-primary/30 overflow-hidden relative"
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
        >
            <Toaster
                theme="dark"
                position="bottom-right"
                toastOptions={{ style: { background: '#1e293b', border: '1px solid #334155', color: 'white' } }}
            />

            <DragDropOverlay visible={isDragging} />

            <AppNav
                connected={remnawave.connected}
                pushStage={pushStage}
                criticalCount={criticalCount}
                warningCount={warningCount}
                hasConfig={!!config}
                onBack={() => navigate('/')}
                onOpenDiagnostics={() => setDiagnosticsOpen(true)}
                onOpenRemnawave={() => setRemnawaveModalOpen(true)}
                onOpenSwitchProfile={() => setRemnawaveModalOpen(true)}
                onPush={pushStage === 'idle' ? () => setPushStage('confirm') : handleRealPush}
                onDisconnect={disconnectRemnawave}
                onOpenAbout={() => setAboutOpen(true)}
                onFileUpload={handleFileUpload}
                onDownload={downloadConfig}
            />

            <main className="flex-1 min-h-0 flex flex-col p-3 md:p-4 max-w-[1800px] mx-auto w-full overflow-hidden">
                {!config ? (
                    <WelcomeScreen
                        presets={getPresets()}
                        onSelectPreset={(cfg) => setConfig(cfg)}
                        onFileUpload={handleFileUpload}
                        onOpenRemnawave={() => setRemnawaveModalOpen(true)}
                    />
                ) : (
                    <ConfigDashboard
                        config={config}
                        rawMode={rawMode}
                        setRawMode={setRawMode}
                        setConfig={setConfig}
                        filteredOutbounds={filteredOutbounds}
                        obSearch={obSearch}
                        setObSearch={setObSearch}
                        modulesVisible={modulesVisible}
                        setModulesVisible={setModulesVisible}
                        onEditInbound={(data, index) => setModal({ type: 'inbound', data, index })}
                        onDeleteInbound={(i) => deleteItem('inbounds', i)}
                        onAddInbound={() => setModal({ type: 'inbound', data: null, index: null })}
                        onOpenInboundJson={() => openSectionJson('inbounds', 'Inbounds')}
                        onEditRouting={() => setModal({ type: 'routing', data: null, index: null })}
                        onOpenRoutingJson={() => openSectionJson('routing', 'Routing')}
                        onEditOutbound={(data, index) => setModal({ type: 'outbound', data, index })}
                        onDeleteOutbound={(i) => deleteItem('outbounds', i)}
                        onMoveOutbound={(from, to) => moveItem('outbounds', from, to)}
                        onAddOutbound={() => setModal({ type: 'outbound', data: null, index: null })}
                        onOpenOutboundJson={() => openSectionJson('outbounds', 'Outbounds')}
                        onBatchImport={() => setBatchModalOpen(true)}
                        onOpenWarpModal={() => setWarpModalOpen(true)}
                        onEditDns={() => { initDns(); setModal({ type: 'dns', data: null, index: null }); }}
                        onOpenDnsJson={() => openSectionJson('dns', 'DNS Config')}
                        onOpenSettings={() => setModal({ type: 'settings', data: null, index: null })}
                        onOpenReverse={() => setModal({ type: 'reverse', data: null, index: null })}
                        onOpenTopology={() => setModal({ type: 'topology', data: null, index: null })}
                        onOpenGeoViewer={() => setGeoViewerOpen(true)}
                        onOpenConfigInspector={() => setConfigInspectorOpen(true)}
                    />
                )}
            </main>

            <ModalManager
                modal={modal}
                onCloseModal={closeModal}
                onSaveModal={handleSaveModal}
                sectionModal={sectionModal}
                onCloseSectionModal={() => setSectionModal({ ...sectionModal, open: false })}
                onSaveSection={handleSaveSection}
                remnawaveModalOpen={remnawaveModalOpen}
                onCloseRemnawave={() => setRemnawaveModalOpen(false)}
                batchModalOpen={batchModalOpen}
                onCloseBatch={() => setBatchModalOpen(false)}
                geoViewerOpen={geoViewerOpen}
                onCloseGeoViewer={() => setGeoViewerOpen(false)}
                diagnosticsOpen={diagnosticsOpen}
                onCloseDiagnostics={() => setDiagnosticsOpen(false)}
                warpModalOpen={warpModalOpen}
                onCloseWarpModal={() => setWarpModalOpen(false)}
                onGenerateWarp={(ob: any) => addItem('outbounds', ob)}
                diagnostics={diagnostics}
                aboutOpen={aboutOpen}
                onCloseAbout={() => setAboutOpen(false)}
                configInspectorOpen={configInspectorOpen}
                onCloseConfigInspector={() => setConfigInspectorOpen(false)}
                setModal={setModal}
                openSectionJson={openSectionJson}
            />
        </div>
    );
}
