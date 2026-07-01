import DeckGL from "@deck.gl/react";
import { Map } from 'react-map-gl';
import { Home, Users, Leaf, BarChart2, Train, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";


type IndicatorId =
    | "prixM2" | "variationPct"
    | "indiceQualiteAir" | "nbEspacesVerts"
    | "population" | "densitePopulation"
    | "nbStationsMetro" | "nbStationsVelib"
    | "tauxCriminalite"
    | "pctLogementsSociaux" | "pctAppartements";

interface IndicatorMeta {
    id: IndicatorId;
    label: string;
    unit: string;
    higherIsBetter: boolean;
    color: string;
    category: "logement" | "social" | "environnement" | "transport" | "securite";
}

interface ViewState {
    longitude: number;
    latitude: number;
    zoom: number;
    pitch: number;
    bearing: number;
}

type Props = {
    geoData: any;
    viewState: ViewState;
    min: number;
    max: number;
    indicatorMeta: IndicatorMeta | undefined;
    layers: any[];
    propertyKey: string;
    setViewState: (viewState: ViewState) => void;
    getColorForValue: (value: number, min: number, max: number, higherIsBetter: boolean, category?: string) => number[];
};

function formatValue(value: number | undefined | null, unit: string): string {
    if (value == null || Number.isNaN(value as number)) return "—";
    const decimals = unit === "%" || unit === "ans" ? 1 : 0;
    return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: decimals }).format(value as number);
}

const CATEGORY_ICONS: Record<string, ReactNode> = {
    logement:     <Home size={13} />,
    social:       <Users size={13} />,
    environnement:<Leaf size={13} />,
    transport:    <Train size={13} />,
    securite:     <ShieldAlert size={13} />,
};


const ParisMaps = ({
    geoData,
    viewState,
    min,
    max,
    indicatorMeta,
    layers,
    propertyKey,
    setViewState,
    getColorForValue,
}: Props) => {


    const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

    return (
        <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)", boxShadow: "0 1px 3px 0 #0000000d" }}>
            <div className="px-4 py-2.5 flex items-center justify-between" style={{ borderBottom: "1px solid var(--border)", backgroundColor: "var(--surface-alt)" }}>
                <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--text)" }}>
                    <span style={{ color: "var(--accent)" }}>
                        {CATEGORY_ICONS[indicatorMeta?.category ?? ""] ?? <BarChart2 size={13} />}
                    </span>
                    {indicatorMeta?.label ?? "Carte choroplèthe"}
                </div>
                <span className="font-mono-data text-xs" style={{ color: "var(--text-3)" }}>
                    {formatValue(min, indicatorMeta?.unit ?? "")} – {formatValue(max, indicatorMeta?.unit ?? "")} {indicatorMeta?.unit}
                </span>
            </div>

            <div className="relative" style={{ height: "65vh" }}>
                {geoData ? (
                    <DeckGL
                        viewState={viewState}
                        onViewStateChange={({ viewState: vs }) => setViewState(vs as ViewState)}
                        controller={true}
                        layers={layers}
                        getTooltip={({ object }) => {
                            if (!object) return null;
                            const rawVal = object.properties[propertyKey];
                            const formattedVal = formatValue(rawVal, indicatorMeta?.unit ?? "");
                            const popRaw = object.properties.value_population;
                            const formattedPop = formatValue(popRaw, "hab");
                            return {
                                html: `
                  <div style="padding:12px;min-width:200px;">
                    <div style="font-weight:700;color:#1A56DB;font-size:13px;margin-bottom:8px;">${object.properties.NOM} Arrondissement</div>
                    <div style="color:#111827;font-size:13px;margin-bottom:4px;">${indicatorMeta?.label} : <span style="font-weight:600;">${formattedVal}${indicatorMeta?.unit ?? ""}</span></div>
                    <div style="color:#6B7280;font-size:11px;">Population : ${formattedPop} hab</div>
                  </div>
                `,
                                style: {
                                    backgroundColor: "#ffffff",
                                    color: "#111827",
                                    border: "1px solid #E5E7EB",
                                    borderRadius: "8px",
                                    fontSize: "13px",
                                    boxShadow: "0 4px 16px rgba(0,0,0,0.10)",
                                },
                            };
                        }}
                    >
                        <Map
                            mapboxAccessToken={MAPBOX_TOKEN}
                            mapStyle="mapbox://styles/mapbox/light-v10"
                            reuseMaps
                            style={{ width: '100%', height: '100%' }}
                        />
                    </DeckGL>
                ) : (
                    <div className="flex items-center justify-center" style={{ height: "65vh", color: "#9CA3AF" }}>
                        <div className="text-center">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 mx-auto mb-2" style={{ borderColor: "#1A56DB" }}></div>
                            <p className="text-sm">Chargement de la carte de Paris…</p>
                        </div>
                    </div>
                )}

                {/* Légende couleur */}
                <div
                    className="absolute bottom-4 left-4 rounded-lg px-3 py-2.5"
                    style={{ backgroundColor: "color-mix(in srgb, var(--surface) 95%, transparent)", backdropFilter: "blur(4px)", border: "1px solid var(--border)", boxShadow: "0 2px 8px 0 #00000014" }}
                >
                    <div className="flex items-center gap-2 text-xs">
                        <span style={{ color: "var(--text-2)" }}>Faible</span>
                        <div className="flex gap-0.5">
                            {[0, 0.25, 0.5, 0.75, 1].map((t) => {
                                const color = getColorForValue(
                                    min + t * (max - min),
                                    min,
                                    max,
                                    indicatorMeta?.higherIsBetter ?? true,
                                    indicatorMeta?.category
                                );
                                return (
                                    <div
                                        key={t}
                                        className="w-6 h-3 rounded-sm"
                                        style={{ backgroundColor: `rgb(${color[0]}, ${color[1]}, ${color[2]})` }}
                                    />
                                );
                            })}
                        </div>
                        <span style={{ color: "var(--text-2)" }}>Élevé</span>
                    </div>
                    {(max - min) < 5 && indicatorMeta?.unit === "%" && (
                        <div className="mt-1.5 text-[10px] leading-tight" style={{ color: "var(--text-3)" }}>
                            Faible variation entre arrondissements
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default ParisMaps;
