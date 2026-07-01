import { useState, useEffect } from "react";
import type { ReactNode } from "react";
import { Home, Users, Leaf, MapPin, BarChart2, Train, ShieldAlert } from "lucide-react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { API_BASE } from "../lib/api";

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
    pctLogementsSociaux: number;
    pctAppartements: number;
}

type IndicatorId =
    | "prixM2" | "variationPct"
    | "indiceQualiteAir" | "nbEspacesVerts"
    | "population" | "densitePopulation"
    | "nbStationsMetro" | "nbStationsVelib"
    | "tauxCriminalite"
    | "pctLogementsSociaux" | "pctAppartements";

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

interface TypologieData {
    type_local: Record<string, number>;
    nb_pieces: Record<string, number>;
}

function formatValue(value: number | undefined | null, unit: string, signed = false): string {
    if (value == null || Number.isNaN(value as number)) return "—";
    const decimals = unit === "%" || unit === "ans" ? 1 : 0;
    const abs = Math.abs(value as number);
    const formatted = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: decimals }).format(signed ? abs : (value as number));
    if (!signed) return formatted;
    return ((value as number) >= 0 ? "+" : "−") + formatted;
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

const TYPE_COLORS: Record<string, string> = {
    Appartement: "#1A56DB",
    Maison:      "#E3522A",
};

const PIECES_COLORS: Record<string, string> = {
    T1:  "#1A56DB",
    T2:  "#4C55AF",
    T3:  "#7F5483",
    T4:  "#B15356",
    "T5+": "#E3522A",
};

const PIECES_ORDER = ["T1", "T2", "T3", "T4", "T5+"];

const Sidebar_details = ({
    INDICATORS_BY_CATEGORY,
    displayData,
    selectedArr,
    selectedIndicator,
    indicatorMeta
}: Props) => {
    const [typologieData, setTypologieData] = useState<TypologieData | null>(null);

    useEffect(() => {
        if (selectedArr == null) { setTypologieData(null); return; }
        fetch(`${API_BASE}/typologie?arr=${selectedArr}`)
            .then((r) => r.ok ? r.json() : null)
            .then((d) => setTypologieData(d))
            .catch(() => setTypologieData(null));
    }, [selectedArr]);

    const typeEntries = typologieData
        ? Object.entries(typologieData.type_local).map(([name, value]) => ({ name, value }))
        : [];

    const piecesEntries = typologieData
        ? PIECES_ORDER
            .filter((k) => typologieData.nb_pieces[k] != null)
            .map((k) => ({ name: k, value: typologieData.nb_pieces[k] }))
        : [];

    return (
        <aside className="w-full lg:w-80 xl:w-96 flex-shrink-0 overflow-y-auto" style={{ backgroundColor: "var(--surface)", borderLeft: "1px solid var(--border)" }}>
            {/* Header */}
            <div className="sticky top-0 z-10 px-5 py-4" style={{ backgroundColor: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
                <h2 className="font-display text-sm font-semibold flex items-center gap-2" style={{ color: "var(--text)" }}>
                    <BarChart2 size={15} style={{ color: "var(--accent)" }} />
                    Profil de l'arrondissement
                </h2>
            </div>

            <div className="px-5 py-4">
                {displayData ? (
                    <div className="space-y-5">
                        {/* Identité */}
                        <div>
                            <div className="font-display text-lg font-bold leading-tight" style={{ color: "var(--text)" }}>
                                {displayData.nom}
                            </div>
                            <div className="text-xs mt-0.5" style={{ color: "var(--text-2)" }}>
                                {formatValue(displayData.population, "hab")} habitants
                            </div>
                            {selectedArr === displayData.arrondissement && (
                                <span
                                    className="inline-block mt-1.5 px-2.5 py-0.5 text-xs rounded-full border"
                                    style={{ backgroundColor: "#1A56DB18", color: "#1A56DB", borderColor: "#1A56DB30" }}
                                >
                                    Sélectionné
                                </span>
                            )}
                        </div>

                        {/* Indicateur principal */}
                        <div className="rounded-xl p-4 border" style={{ backgroundColor: (indicatorMeta?.color ?? "#1A56DB") + "12", borderColor: (indicatorMeta?.color ?? "#1A56DB") + "30" }}>
                            <div className="text-xs font-medium mb-1.5" style={{ color: indicatorMeta?.color }}>
                                {indicatorMeta?.label}
                            </div>
                            <div className="font-mono-data text-2xl font-bold" style={{ color: "var(--text)" }}>
                                {formatValue(displayData[selectedIndicator], "", selectedIndicator === "variationPct")}
                                <span className="text-sm ml-1 font-normal" style={{ color: (indicatorMeta?.color ?? "#6B7280") + "99" }}>
                                    {indicatorMeta?.unit}
                                </span>
                            </div>
                        </div>

                        {/* Grille des indicateurs par catégorie */}
                        <div className="space-y-4">
                            {Object.entries(INDICATORS_BY_CATEGORY).map(([category, indicators]) => (
                                <div key={category}>
                                    <div
                                        className="text-[10px] font-bold uppercase tracking-widest mb-2 flex items-center gap-1.5"
                                        style={{ color: "var(--text-3)" }}
                                    >
                                        {CATEGORY_ICONS[category]}
                                        {CATEGORY_LABELS[category] ?? category}
                                    </div>
                                    <div className="grid grid-cols-2 gap-2">
                                        {indicators.map((ind) => {
                                            const val = displayData[ind.id as IndicatorId];
                                            const isActive = ind.id === selectedIndicator;
                                            return (
                                                <div
                                                    key={ind.id}
                                                    className="rounded-xl border p-3 transition-all"
                                                    style={{
                                                        backgroundColor: isActive ? ind.color + "10" : "var(--surface)",
                                                        borderColor: isActive ? ind.color + "50" : "#E5E7EB",
                                                        boxShadow: isActive ? `0 0 0 1.5px ${ind.color}30` : "0 1px 3px 0 #0000000d",
                                                    }}
                                                >
                                                    <div className="flex items-center gap-1.5 mb-1.5">
                                                        <span
                                                            className="w-2 h-2 rounded-full flex-shrink-0"
                                                            style={{ backgroundColor: ind.color }}
                                                        />
                                                        <span className="text-[10px] font-medium leading-tight" style={{ color: "var(--text-2)" }}>
                                                            {ind.label}
                                                        </span>
                                                    </div>
                                                    <div className="font-mono-data font-bold text-sm leading-none" style={{ color: "var(--text)" }}>
                                                        {formatValue(val, "", ind.id === "variationPct")}
                                                        {!Number.isNaN(val as number) && val != null && (
                                                            <span className="text-[10px] font-normal ml-0.5" style={{ color: "var(--text-3)" }}>
                                                                {ind.unit}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* Donuts — Typologie des logements */}
                        {typologieData && (typeEntries.length > 0 || piecesEntries.length > 0) && (
                            <div>
                                <div className="text-[10px] font-bold uppercase tracking-widest mb-3 flex items-center gap-1.5" style={{ color: "var(--text-3)" }}>
                                    <Home size={13} />
                                    Typologie des logements
                                </div>
                                <div className="space-y-4">
                                    {typeEntries.length > 0 && (
                                        <div className="rounded-xl border p-3" style={{ borderColor: "var(--border)", boxShadow: "0 1px 3px 0 #0000000d" }}>
                                            <div className="text-xs font-medium mb-2" style={{ color: "var(--text-2)" }}>Type de bien</div>
                                            <ResponsiveContainer width="100%" height={130}>
                                                <PieChart>
                                                    <Pie
                                                        data={typeEntries}
                                                        cx="50%"
                                                        cy="50%"
                                                        innerRadius={38}
                                                        outerRadius={55}
                                                        dataKey="value"
                                                        paddingAngle={2}
                                                    >
                                                        {typeEntries.map((entry) => (
                                                            <Cell key={entry.name} fill={TYPE_COLORS[entry.name] ?? "#9CA3AF"} />
                                                        ))}
                                                    </Pie>
                                                    <Tooltip
                                                        formatter={(v) => [`${Number(v ?? 0).toFixed(1)} %`, ""]}
                                                        contentStyle={{ backgroundColor: "#1A56DB", border: "none", borderRadius: 8, color: "#fff", fontSize: 11 }}
                                                        itemStyle={{ color: "#fff" }}
                                                        labelStyle={{ display: "none" }}
                                                    />
                                                </PieChart>
                                            </ResponsiveContainer>
                                            <div className="flex flex-wrap gap-2 mt-1">
                                                {typeEntries.map((e) => (
                                                    <span key={e.name} className="flex items-center gap-1 text-[11px]" style={{ color: "var(--text-2)" }}>
                                                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: TYPE_COLORS[e.name] ?? "#9CA3AF" }} />
                                                        {e.name} — {e.value.toFixed(1)} %
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {piecesEntries.length > 0 && (
                                        <div className="rounded-xl border p-3" style={{ borderColor: "var(--border)", boxShadow: "0 1px 3px 0 #0000000d" }}>
                                            <div className="text-xs font-medium mb-2" style={{ color: "var(--text-2)" }}>Nombre de pièces</div>
                                            <ResponsiveContainer width="100%" height={130}>
                                                <PieChart>
                                                    <Pie
                                                        data={piecesEntries}
                                                        cx="50%"
                                                        cy="50%"
                                                        innerRadius={38}
                                                        outerRadius={55}
                                                        dataKey="value"
                                                        paddingAngle={2}
                                                    >
                                                        {piecesEntries.map((entry) => (
                                                            <Cell key={entry.name} fill={PIECES_COLORS[entry.name] ?? "#9CA3AF"} />
                                                        ))}
                                                    </Pie>
                                                    <Tooltip
                                                        formatter={(v) => [`${Number(v ?? 0).toFixed(1)} %`, ""]}
                                                        contentStyle={{ backgroundColor: "#1A56DB", border: "none", borderRadius: 8, color: "#fff", fontSize: 11 }}
                                                        itemStyle={{ color: "#fff" }}
                                                        labelStyle={{ display: "none" }}
                                                    />
                                                </PieChart>
                                            </ResponsiveContainer>
                                            <div className="flex flex-wrap gap-2 mt-1">
                                                {piecesEntries.map((e) => (
                                                    <span key={e.name} className="flex items-center gap-1 text-[11px]" style={{ color: "var(--text-2)" }}>
                                                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: PIECES_COLORS[e.name] ?? "#9CA3AF" }} />
                                                        {e.name} — {e.value.toFixed(1)} %
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="text-center py-16">
                        <MapPin size={36} className="mx-auto mb-3" style={{ color: "#D1D5DB" }} />
                        <div className="text-sm font-semibold mb-1" style={{ color: "var(--text-2)" }}>
                            Explorez Paris arrondissement par arrondissement
                        </div>
                        <p className="text-xs leading-relaxed" style={{ color: "var(--text-3)" }}>
                            Cliquez sur un arrondissement pour explorer ses indicateurs
                        </p>
                    </div>
                )}
            </div>
        </aside>
    );
};

export default Sidebar_details;
