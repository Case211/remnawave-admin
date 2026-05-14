// @ts-nocheck
import React from "react";
import { Icon } from "../ui";
import { Button } from "../ui";
import { JsonField } from "../ui";
import { DndContext, closestCenter } from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { XrayConfig } from "../../core/types";

// Re-usable column Card for the dashboard
interface DashCardProps {
  title: string;
  icon: string;
  color: string;
  actions: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

const DashCard = ({
  title,
  icon,
  color,
  children,
  actions,
  className = "",
}: DashCardProps) => (
  <div
    className={`bg-slate-800 border border-slate-700/50 rounded-xl flex flex-col hover:border-slate-600 transition-colors shadow-xl overflow-hidden ${className}`}
  >
    <div className="flex justify-between items-center p-4 border-b border-slate-700/50 bg-slate-800/50 shrink-0 h-16">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-xl ${color} text-white shadow-lg ring-1 ring-white/10`}>
          <Icon name={icon} className="text-xl" />
        </div>
        <h2 className="text-lg font-bold text-slate-100 tracking-tight">{title}</h2>
      </div>
      <div className="flex items-center gap-2">
        {actions}
      </div>
    </div>
    <div className="flex-1 p-4 space-y-3 overflow-y-auto custom-scroll bg-slate-900/30 min-h-0">
      {children}
    </div>
  </div>
);

const SortableOutboundItem = ({
  ob,
  onEdit,
  onDelete,
  onMove,
  totalCount,
}: any) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: `ob-${ob.i}` });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 50 : "auto",
    position: "relative" as const,
  };

  const handleIndexChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseInt(e.target.value);
    if (!isNaN(val)) {
      const target = Math.max(0, Math.min(totalCount - 1, val));
      if (target !== ob.i) onMove(ob.i, target);
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`card-item group flex justify-between items-start gap-2 ${isDragging ? "opacity-50 ring-2 ring-indigo-500 bg-indigo-950/20" : ""}`}
    >
      <div className="flex items-center gap-3 shrink-0 py-2 px-3">
        <div
          {...listeners}
          {...attributes}
          className="cursor-grab text-slate-700 hover:text-slate-400 transition-colors duration-300 touch-none"
        >
          <Icon name="DotsSixVertical" weight="bold" className="text-lg" />
        </div>
        
        <div className="text-xl font-black text-slate-600/40 italic tabular-nums w-6 text-center select-none">
          {ob.i}
        </div>
      </div>

      <div className="w-px h-8 bg-slate-800/80 self-center shrink-0" />

      <div className="min-w-0 flex-1 py-2 pl-3 flex flex-col justify-center">
        <div className="font-bold text-blue-400 text-sm flex items-center gap-2 truncate">
          <Icon name="PaperPlaneRight" weight="bold" className="text-[10px] opacity-40" />
          {ob.tag || "no-tag"}
        </div>
        <div className="text-[10px] text-slate-500 mt-0.5 font-mono truncate opacity-80">
          {ob.protocol}
          {ob.protocol !== "freedom" && ob.protocol !== "blackhole" && (
            <>
              <span className="mx-1 text-slate-700">•</span>
              {ob.settings?.vnext?.[0]?.address ||
                ob.settings?.servers?.[0]?.address ||
                ob.settings?.address ||
                "no-address"}
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1 shrink-0 px-2 self-center md:opacity-0 md:group-hover:opacity-100 transition-all duration-500 ease-in-out">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onEdit(ob, ob.i)}
          icon="PencilSimple"
          title="Редактировать"
          className="h-8 w-8 p-0 text-slate-500 hover:text-white hover:bg-transparent transition-all duration-300"
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDelete(ob.i)}
          icon="Trash"
          title="Удалить"
          className="h-8 w-8 p-0 text-slate-500 hover:!text-rose-500 hover:bg-transparent transition-all duration-300"
        />
      </div>
    </div>
  );
};

interface ConfigDashboardProps {
  config: XrayConfig;
  rawMode: boolean;
  setRawMode: (v: boolean) => void;
  setConfig: (cfg: XrayConfig | null) => void;
  onEditInbound: (data: any, index: number | null) => void;
  onDeleteInbound: (index: number) => void;
  onOpenInboundJson: () => void;
  onAddInbound: () => void;
  onEditRouting: () => void;
  onOpenRoutingJson: () => void;
  onEditOutbound: (data: any, index: number | null) => void;
  onDeleteOutbound: (index: number) => void;
  onMoveOutbound: (fromIndex: number, toIndex: number) => void;
  onOpenOutboundJson: () => void;
  onAddOutbound: () => void;
  onBatchImport: () => void;
  onOpenWarpModal: () => void;
  onEditDns: () => void;
  onOpenDnsJson: () => void;
  filteredOutbounds: any[];
  obSearch: string;
  setObSearch: (v: string) => void;
  modulesVisible: boolean;
  setModulesVisible: (v: boolean) => void;
  onOpenSettings: () => void;
  onOpenReverse: () => void;
  onOpenTopology: () => void;
  onOpenGeoViewer: () => void;
  onOpenConfigInspector: () => void;
}

export const ConfigDashboard = ({
  config,
  rawMode,
  setRawMode,
  setConfig,
  onEditInbound,
  onDeleteInbound,
  onOpenInboundJson,
  onAddInbound,
  onEditRouting,
  onOpenRoutingJson,
  onEditOutbound,
  onDeleteOutbound,
  onMoveOutbound,
  onOpenOutboundJson,
  onAddOutbound,
  onBatchImport,
  onOpenWarpModal,
  onEditDns,
  onOpenDnsJson,
  filteredOutbounds,
  obSearch,
  setObSearch,
  modulesVisible,
  setModulesVisible,
  onOpenSettings,
  onOpenReverse,
  onOpenTopology,
  onOpenGeoViewer,
  onOpenConfigInspector,
}: ConfigDashboardProps) => {
  const handleDragEnd = (event: any) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIdx = parseInt(active.id.replace("ob-", ""));
    const newIdx = parseInt(over.id.replace("ob-", ""));

    onMoveOutbound(oldIdx, newIdx);
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-3">
      {/* Toolbar */}
      <div className="shrink-0 flex flex-col md:flex-row justify-between items-start md:items-center bg-slate-900 border border-slate-800 p-3 md:p-4 rounded-xl shadow-lg gap-4">
        <div className="flex flex-col md:flex-row items-start md:items-center gap-4 w-full md:w-auto">
          <div className="flex items-center justify-between w-full md:w-auto">
            <h2 className="font-bold text-slate-300 flex items-center gap-2 text-sm md:text-base">
              <Icon name="SlidersHorizontal" /> Модули ядра
            </h2>
            <button
              onClick={() => setModulesVisible(!modulesVisible)}
              className="md:hidden p-2 text-slate-400 hover:text-white transition-colors"
            >
              <Icon
                name={modulesVisible ? "CaretUp" : "CaretDown"}
                weight="bold"
              />
            </button>
          </div>

          <div className="hidden md:block w-px h-6 bg-slate-800" />

          <div
            className={`${modulesVisible ? "flex" : "hidden md:flex"} flex-wrap gap-2 w-full md:w-auto animate-in fade-in slide-in-from-top-1 duration-200`}
          >
            <Button
              className="flex-1 md:flex-none text-[10px] md:text-xs py-1.5 md:py-2"
              variant="secondary"
              onClick={onOpenSettings}
              icon="Gear"
            >
              Настройки ядра
            </Button>
            <Button
              className="flex-1 md:flex-none text-[10px] md:text-xs py-1.5 md:py-2"
              variant="secondary"
              onClick={onOpenReverse}
              icon="ArrowsLeftRight"
            >
              Reverse-прокси
            </Button>
            <Button
              className="flex-1 md:flex-none text-[10px] md:text-xs py-1.5 md:py-2"
              variant="secondary"
              onClick={onOpenTopology}
              icon="GitMerge"
            >
              Топология
            </Button>
            <Button
              className="flex-1 md:flex-none text-[10px] md:text-xs py-1.5 md:py-2"
              variant="secondary"
              onClick={onOpenGeoViewer}
              icon="GlobeHemisphereWest"
            >
              Geo-просмотр
            </Button>
            <Button
              className="flex-1 md:flex-none text-[10px] md:text-xs py-1.5 md:py-2 border-indigo-500/30 text-indigo-300 hover:bg-indigo-500/10"
              variant="secondary"
              onClick={onOpenConfigInspector}
              icon="FileSearch"
            >
              Инспектор конфига
            </Button>
          </div>
        </div>

        <div
          className={`${modulesVisible ? "flex" : "hidden md:flex"} flex-wrap gap-2 w-full md:w-auto pt-3 md:pt-0 border-t border-slate-800 md:border-transparent animate-in fade-in slide-in-from-top-1 duration-200`}
        >
          <Button
            variant="secondary"
            onClick={() => setRawMode(!rawMode)}
            icon={rawMode ? "Layout" : "Code"}
            className={`flex-1 md:flex-none text-[10px] md:text-xs py-1.5 md:py-2 ${rawMode ? "bg-indigo-600 border-indigo-500 text-white shadow-lg shadow-indigo-500/20" : ""}`}
          >
            {rawMode ? "UI-режим" : "JSON-режим"}
          </Button>
          <Button
            variant="danger"
            className="text-[10px] md:text-xs px-3 py-1.5 md:py-2 flex-1 md:flex-none"
            onClick={() => {
              if (confirm("Очистить конфиг?")) setConfig(null as any);
            }}
            icon="XCircle"
            title="Закрыть конфиг"
          >
            <span className="md:inline">Очистить</span>
          </Button>
        </div>
      </div>

      {/* Content */}
      {rawMode ? (
        <div className="flex-1 min-h-0 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden p-4 shadow-2xl flex flex-col">
          <JsonField
            label="Полный конфиг (авто-сохранение)"
            value={config}
            onChange={(newConfig: any) => {
              if (newConfig) setConfig(newConfig);
            }}
            className="flex-1 relative min-h-0"
          />
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col gap-3 overflow-y-auto custom-scroll pb-6">
          <div className="flex flex-col xl:grid xl:grid-cols-3 gap-3 xl:flex-1 xl:min-h-0">
            {/* Inbounds */}
            <DashCard
              title={`Inbounds (${config.inbounds?.length || 0})`}
              icon="ArrowCircleDown"
              color="bg-emerald-600"
              className="h-[400px] xl:h-full xl:min-h-0 shrink-0 xl:shrink"
              actions={
                <div className="flex items-center bg-slate-950/50 p-1 rounded-lg border border-slate-700/50 gap-1 h-11">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onOpenInboundJson}
                    icon="Code"
                    title="Открыть JSON"
                    className="h-9 w-9 p-0"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onAddInbound}
                    icon="Plus"
                    title="Добавить inbound"
                    className="h-9 w-9 p-0"
                  />
                </div>
              }
            >
              {(config.inbounds || []).map((ib: any, i: number) => (
                <div
                  key={i}
                  className="card-item group flex justify-between items-stretch gap-0"
                >
                  <div className="flex items-center gap-3 shrink-0 py-2 px-3">
                    <div className="text-slate-700 py-1">
                      <Icon name="Hash" weight="bold" className="text-lg" />
                    </div>
                    <div className="text-xl font-black text-slate-600/40 italic tabular-nums w-6 text-center select-none">
                      {i}
                    </div>
                  </div>

                  <div className="w-px h-8 bg-slate-800/80 self-center shrink-0" />

                  <div className="min-w-0 flex-1 py-2 pl-3 flex flex-col justify-center">
                    <div className="font-bold text-emerald-400 text-sm flex items-center gap-2 truncate">
                      <Icon name="ArrowCircleDown" weight="bold" className="text-[10px] opacity-40" />
                      {ib.tag || "no-tag"}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5 font-mono truncate opacity-80">
                      {ib.protocol} <span className="mx-1 text-slate-700">•</span> {ib.port}
                    </div>
                  </div>

                  <div className="flex items-center gap-1 px-2 md:opacity-0 md:group-hover:opacity-100 transition-all duration-500 ease-in-out self-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onEditInbound(ib, i)}
                      icon="PencilSimple"
                      title="Редактировать"
                      className="h-8 w-8 p-0 text-slate-500 hover:text-white hover:bg-transparent transition-all duration-300"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onDeleteInbound(i)}
                      icon="Trash"
                      title="Удалить"
                      className="h-8 w-8 p-0 text-slate-500 hover:!text-rose-500 hover:bg-transparent transition-all duration-300"
                    />
                  </div>
                </div>
              ))}
            </DashCard>

            {/* Routing */}
            <DashCard
              title="Маршрутизация"
              icon="ArrowsSplit"
              color="bg-purple-600"
              className="h-[400px] xl:h-full xl:min-h-0 shrink-0 xl:shrink"
              actions={
                <div className="flex items-center bg-slate-950/50 p-1 rounded-lg border border-slate-700/50 gap-1 h-11">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onOpenRoutingJson}
                    icon="Code"
                    title="Открыть JSON"
                    className="h-9 w-9 p-0"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onEditRouting}
                    icon="PencilSimple"
                    title="Редактировать маршруты"
                    className="h-9 w-9 p-0"
                  />
                </div>
              }
            >
              <div className="text-xs text-center text-purple-300 bg-purple-900/20 p-2 rounded mb-2 border border-purple-500/20 flex justify-between px-4 shrink-0">
                <span className="opacity-70">Стратегия:</span>
                <span className="font-bold text-white">
                  {config.routing?.domainStrategy || "AsIs"}
                </span>
              </div>
              <div className="space-y-2">
                {(config.routing?.rules || [])
                  .slice(0, 20)
                  .map((rule: any, i: number) => {
                    const hasName = !!rule.ruleTag;
                    const conditions: string[] = [];
                    if (rule.domain) conditions.push(`${rule.domain.length} dom`);
                    if (rule.ip) conditions.push(`${rule.ip.length} ip`);
                    if (rule.port) conditions.push("port");
                    if (rule.protocol) conditions.push("proto");
                    if (rule.inboundTag) conditions.push("inbound");
                    if (conditions.length === 0) conditions.push("match all");
                    
                    const isBalancer = !!rule.balancerTag;
                    const target = rule.outboundTag || rule.balancerTag || "null";
                    
                    return (
                      <div
                        key={i}
                        className="card-item group flex justify-between items-stretch gap-0"
                      >
                        <div className="flex items-center gap-3 shrink-0 py-2 px-3">
                          <div className="flex items-center justify-center w-5">
                             <div className={`w-2.5 h-2.5 rounded-full ring-4 ${isBalancer ? "bg-purple-500 ring-purple-500/10" : "bg-blue-500 ring-blue-500/10"}`} />
                          </div>
                          <div className="text-xl font-black text-slate-600/40 italic tabular-nums w-6 text-center select-none">
                            {i}
                          </div>
                        </div>

                        <div className="w-px h-8 bg-slate-800/80 self-center shrink-0" />

                        <div className="min-w-0 flex-1 py-2 pl-3 flex flex-col justify-center">
                          <div className="flex justify-between items-center pr-2 gap-2">
                            <span className={`text-sm font-bold truncate ${hasName ? "text-white" : "text-slate-400 font-mono"}`}>
                              {rule.ruleTag || conditions.join(", ")}
                            </span>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <Icon name="ArrowRight" className="text-slate-700 text-[10px]" />
                              <span className={`font-mono font-bold text-[10px] px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 max-w-[100px] truncate ${isBalancer ? "text-purple-400" : "text-blue-400"}`}>
                                {target}
                              </span>
                            </div>
                          </div>
                          {hasName && (
                            <div className="text-[10px] text-slate-500 font-mono truncate opacity-80 mt-0.5">
                              {conditions.join(", ")}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                {(config.routing?.rules || []).length === 0 && (
                  <div className="text-center text-slate-600 py-8 italic text-xs">
                    Правил маршрутизации нет.
                    <br />
                    Трафик пойдёт через первый outbound.
                  </div>
                )}
                {(config.routing?.rules || []).length > 20 && (
                  <div className="text-center text-xs text-slate-500 italic pt-2 border-t border-slate-800">
                    ...ещё {(config.routing?.rules || []).length - 20} правил
                  </div>
                )}
              </div>
            </DashCard>

            {/* Outbounds */}
            <DashCard
              title={`Outbounds (${config.outbounds?.length || 0})`}
              icon="ArrowCircleUp"
              color="bg-blue-600"
              className="h-[400px] xl:h-full xl:min-h-0 shrink-0 xl:shrink"
              actions={
                <div className="flex gap-2 items-center">
                  <div className="relative hidden md:flex h-11 items-center">
                    <Icon
                      name="MagnifyingGlass"
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm"
                    />
                    <input
                      className="bg-slate-950/50 border border-slate-700/50 rounded-xl pl-9 pr-3 h-full w-32 outline-none focus:w-64 focus:border-indigo-500 transition-all text-white text-xs placeholder:text-slate-600 shadow-inner"
                      placeholder="Фильтр по IP, тэгу..."
                      value={obSearch}
                      onChange={(e) => setObSearch(e.target.value)}
                    />
                  </div>

                  <div className="flex items-center bg-slate-950/50 p-1 rounded-xl border border-slate-700/50 gap-1 h-11">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={onOpenWarpModal}
                      icon="Lightning"
                      title="Сгенерировать WARP outbound"
                      className="h-9 w-9 p-0 text-amber-500 hover:text-amber-400"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={onBatchImport}
                      icon="Stack"
                      title="Массовый импорт / экспорт"
                      className="h-9 w-9 p-0"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={onOpenOutboundJson}
                      icon="Code"
                      title="Открыть JSON"
                      className="h-9 w-9 p-0"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={onAddOutbound}
                      icon="Plus"
                      title="Добавить outbound"
                      className="h-9 w-9 p-0"
                    />
                  </div>
                </div>
              }
            >
              <div className="md:hidden mb-3 relative shrink-0">
                <Icon
                  name="MagnifyingGlass"
                  className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500"
                />
                <input
                  className="input-base pl-8 text-xs py-2 bg-slate-950/50"
                  placeholder="Поиск по outbounds..."
                  value={obSearch}
                  onChange={(e) => setObSearch(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <DndContext
                  collisionDetection={closestCenter}
                  onDragEnd={handleDragEnd}
                >
                  <SortableContext
                    items={filteredOutbounds.map((ob) => `ob-${ob.i}`)}
                    strategy={verticalListSortingStrategy}
                  >
                    {filteredOutbounds.length > 0 ? (
                      filteredOutbounds.map((ob: any) => (
                        <SortableOutboundItem
                          key={ob.i}
                          ob={ob}
                          totalCount={config.outbounds?.length || 0}
                          onEdit={onEditOutbound}
                          onDelete={onDeleteOutbound}
                          onMove={onMoveOutbound}
                        />
                      ))
                    ) : (
                      <div className="text-center py-10 opacity-50">
                        <Icon
                          name="MagnifyingGlass"
                          className="mx-auto text-3xl mb-2"
                        />
                        <p className="text-xs">
                          Ничего не нашлось
                        </p>
                      </div>
                    )}
                  </SortableContext>
                </DndContext>
              </div>
            </DashCard>
          </div>

          {/* DNS */}
          <DashCard
            title="DNS"
            icon="Globe"
            color="bg-indigo-600"
            className="shrink-0 w-full"
            actions={
              <div className="flex items-center bg-slate-950/50 p-1 rounded-lg border border-slate-700/50 gap-1 h-11">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onOpenDnsJson}
                  icon="Code"
                  title="Открыть JSON"
                  className="h-9 w-9 p-0"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onEditDns}
                  icon="PencilSimple"
                  title="Редактировать DNS"
                  className="h-9 w-9 p-0"
                />
              </div>
            }
          >
            {config.dns ? (
              <div className="flex flex-col md:flex-row gap-4 items-stretch md:items-center">
                <div className="grid grid-cols-2 gap-2 text-xs flex-1">
                  <div className="bg-slate-900 p-2 rounded border border-slate-700/50 flex items-center justify-between px-4">
                    <span className="text-slate-500 block text-[10px] uppercase">
                      Серверов
                    </span>
                    <span className="text-white font-bold font-mono text-lg">
                      {config.dns.servers?.length || 0}
                    </span>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-700/50 flex items-center justify-between px-4">
                    <span className="text-slate-500 block text-[10px] uppercase">
                      Хостов
                    </span>
                    <span className="text-white font-bold font-mono text-lg">
                      {Object.keys(config.dns.hosts || {}).length}
                    </span>
                  </div>
                </div>
                <div className="text-xs text-slate-400 md:border-l border-slate-800 md:pl-4 flex flex-col gap-1 min-w-[200px]">
                  <div className="flex justify-between">
                    <span>Стратегия:</span>
                    <span className="text-indigo-300 font-bold">
                      {config.dns.queryStrategy || "UseIP"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Client IP:</span>
                    <span className="font-mono text-slate-500">
                      {config.dns.clientIp || "—"}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-4 text-slate-500 text-xs">
                DNS не настроен. Нажмите «Редактировать», чтобы создать с дефолтами.
              </div>
            )}
          </DashCard>
        </div>
      )}
    </div>
  );
};
