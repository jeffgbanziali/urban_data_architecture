import type { ReactNode } from "react";
import { Home, Users, Leaf, MapPin, BarChart2, Train, ShieldAlert } from "lucide-react";

interface UrbanDataItem {
    arrondissement: number;
    nom: string;
    prixM2: number;
    variationPct: number;
    indiceQualiteAir: number;
    nbEspacesVerts: number;
    population: number;
    densitePopulation: number;
    nbStationsMetro: number;
    nbStationsVelib: number;
    tauxCriminalite: number;
}

type IndicatorId =
    | "prixM2" | "variationPct"
    | "indiceQualiteAir" | "nbEspacesVerts"
    | "population" | "densitePopulation"
    | "nbStationsMetro" | "nbStationsVelib"
    | "tauxCriminalite";

type Category = "logement" | "social" | "environnement" | "transport" | "securite";

interface IndicatorMeta {
    id: IndicatorId;
    label: string;
    unit: string;
    higherIsBetter: boolean;
    color: string;
    category: Category;
}

type IndicatorsByCategory = {
    [key: string]: IndicatorMeta[];
};

type Props = {
    INDICATORS_BY_CATEGORY: IndicatorsByCategory;
    displayData: UrbanDataItem | undefined;
    selectedArr: number | null;
    selectedIndicator: IndicatorId;
    indicatorMeta: IndicatorMeta | undefined;
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

const CATEGORY_LABELS: Record<string, string> = {
    logement:     "Logement",
    social:       "Démographie",
    environnement:"Environnement",
    transport:    "Transport",
    securite:     "Sécurité",
};

const Sidebar_details = ({
    INDICATORS_BY_CATEGORY,
    displayData,
    selectedArr,
    selectedIndicator,
    indicatorMeta
}: Props) => {
    return (
        <aside className="w-full lg:w-80 xl:w-96 bg-white border-l border-hairline flex-shrink-0 overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 bg-white border-b border-hairline px-5 py-4 z-10">
                <h2 className="font-display text-sm font-semibold text-ink flex items-center gap-2">
                    <BarChart2 size={15} className="text-terracotta" />
                    Profil de l'arrondissement
                </h2>
            </div>

            <div className="px-5 py-4">
                {displayData ? (
                    <div className="space-y-5">
                        {/* Identité */}
                        <div>
                            <div className="font-display text-lg font-bold text-ink leading-tight">
                                {displayData.nom}
                            </div>
                            <div className="text-ink/50 text-xs mt-0.5">
                                {formatValue(displayData.population, "hab")} habitants
                            </div>
                            {selectedArr === displayData.arrondissement && (
                                <span className="inline-block mt-1.5 px-2.5 py-0.5 bg-terracotta/10 text-terracotta text-xs rounded-full border border-terracotta/20">
                                    Sélectionné
                                </span>
                            )}
                        </div>

                        {/* Indicateur principal */}
                        <div className="bg-cream rounded-xl p-4 border border-hairline">
                            <div className="text-ink/40 text-xs mb-1.5">{indicatorMeta?.label}</div>
                            <div className="font-mono-data text-2xl font-bold" style={{ color: indicatorMeta?.color }}>
                                {formatValue(displayData[selectedIndicator], "")}
                                <span className="text-sm text-ink/40 ml-1 font-normal">{indicatorMeta?.unit}</span>
                            </div>
                        </div>

                        {/* Indicateurs par catégorie */}
                        <div className="space-y-4">
                            {Object.entries(INDICATORS_BY_CATEGORY).map(([category, indicators]) => (
                                <div key={category}>
                                    <div className="text-ink/40 text-[10px] font-bold uppercase tracking-widest mb-2 flex items-center gap-1.5">
                                        {CATEGORY_ICONS[category]}
                                        {CATEGORY_LABELS[category] ?? category}
                                    </div>
                                    <div className="space-y-1">
                                        {indicators.map((ind) => {
                                            const val = displayData[ind.id as IndicatorId];
                                            const isActive = ind.id === selectedIndicator;
                                            return (
                                                <div
                                                    key={ind.id}
                                                    className={`flex justify-between items-center py-1.5 px-2.5 rounded-lg text-sm transition-colors ${
                                                        isActive
                                                            ? "bg-cream border border-hairline"
                                                            : "hover:bg-cream/60"
                                                    }`}
                                                >
                                                    <span className={isActive ? "text-ink font-medium" : "text-ink/60"}>
                                                        {ind.label}
                                                    </span>
                                                    <span className="font-mono-data font-semibold text-ink text-xs">
                                                        {formatValue(val, "")}
                                                        {!Number.isNaN(val as number) && val != null && (
                                                            <span className="text-ink/35 ml-0.5">{ind.unit}</span>
                                                        )}
                                                    </span>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                ) : (
                    <div className="text-center py-16 text-ink/30">
                        <MapPin size={36} className="mx-auto mb-3 text-ink/15" />
                        <div className="text-sm font-medium text-ink/50 mb-1">
                            Aucun arrondissement sélectionné
                        </div>
                        <p className="text-xs text-ink/30 leading-relaxed">
                            Cliquez sur la carte pour explorer les données
                        </p>
                    </div>
                )}
            </div>
        </aside>
    );
};

export default Sidebar_details;
