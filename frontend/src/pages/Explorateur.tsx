import React, { useEffect, useMemo, useState } from "react";
import { GeoJsonLayer } from "@deck.gl/layers";
import "mapbox-gl/dist/mapbox-gl.css";
import { BarChart2, TrendingUp, Wind, Users, Train, ShieldAlert, ChevronDown, X } from "lucide-react";
import Sidebar_details from "../components/Sidebar_details";
import Graphics from "../components/Graphics";
import ParisMaps from "../components/ParisMaps";

// ─── Types ───────────────────────────────────────────────────────────────────

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
  | "population" | "densitePopulation"
  | "indiceQualiteAir" | "nbEspacesVerts"
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
  hasYearDimension?: boolean;
}

// ─── Constantes ──────────────────────────────────────────────────────────────

const INDICATORS: IndicatorMeta[] = [
  { id: "prixM2",           label: "Prix immobilier",     unit: "€/m²",         higherIsBetter: false, color: "#dc2626", category: "logement",     hasYearDimension: true },
  { id: "variationPct",     label: "Variation annuelle",  unit: "%",             higherIsBetter: false, color: "#f97316", category: "logement",     hasYearDimension: true },
  { id: "population",       label: "Population",          unit: "hab",           higherIsBetter: true,  color: "#ec4899", category: "social" },
  { id: "densitePopulation",label: "Densité",             unit: "hab/km²",       higherIsBetter: false, color: "#f59e0b", category: "social" },
  { id: "indiceQualiteAir", label: "Qualité de l'air",    unit: "/100",          higherIsBetter: true,  color: "#7c3aed", category: "environnement" },
  { id: "nbEspacesVerts",   label: "Espaces verts",       unit: "lieux",         higherIsBetter: true,  color: "#16a34a", category: "environnement" },
  { id: "nbStationsMetro",  label: "Stations Métro/RER",  unit: "stations",      higherIsBetter: true,  color: "#0284c7", category: "transport" },
  { id: "nbStationsVelib",  label: "Stations Vélib",      unit: "stations",      higherIsBetter: true,  color: "#0891b2", category: "transport" },
  { id: "tauxCriminalite",  label: "Criminalité",         unit: "faits/1000hab", higherIsBetter: false, color: "#be123c", category: "securite" },
];

const CATEGORIES: { id: Category; label: string; icon: React.ReactNode }[] = [
  { id: "logement",     label: "Logement",      icon: <BarChart2 size={14} /> },
  { id: "social",       label: "Démographie",   icon: <Users size={14} /> },
  { id: "environnement",label: "Environnement", icon: <Wind size={14} /> },
  { id: "transport",    label: "Transport",      icon: <Train size={14} /> },
  { id: "securite",     label: "Sécurité",       icon: <ShieldAlert size={14} /> },
];

const AVAILABLE_YEARS = [2021, 2022, 2023, 2024, 2025];

const GOLD_FIELD: Record<IndicatorId, string> = {
  prixM2:            "prixM2",
  variationPct:      "variationPct",
  population:        "population",
  densitePopulation: "densite_hab_km2",
  indiceQualiteAir:  "indice_qualite_air",
  nbEspacesVerts:    "nb_espaces_verts",
  nbStationsMetro:   "nb_stations_metro",
  nbStationsVelib:   "nb_stations_velib",
  tauxCriminalite:   "taux_criminalite",
};

const ARR_COLORS = ["#C1502D", "#1C2E4A", "#4F7A6F", "#f97316", "#7c3aed", "#16a34a"];
const arrLabel = (n: number) => (n === 1 ? "1er" : `${n}e`);

const INDICATORS_BY_CATEGORY = Object.fromEntries(
  CATEGORIES.map((c) => [c.id, INDICATORS.filter((i) => i.category === c.id)])
) as Record<Category, IndicatorMeta[]>;

const API_BASE = (import.meta as any).env?.VITE_API_BASE || "http://localhost:8000";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function propertyKeyFor(id: IndicatorId, year: number): string {
  const field = GOLD_FIELD[id];
  return INDICATORS.find((i) => i.id === id)?.hasYearDimension
    ? `value_${field}_${year}`
    : `value_${field}`;
}

// Palettes multi-stops par catégorie (t=0 = pire, t=1 = meilleur)
const PALETTES: Record<string, Array<[number, number, number]>> = {
  logement:     [[248, 242, 228], [180, 120, 70], [28, 46, 74]],   // cream → navy
  social:       [[245, 238, 255], [130, 85, 195], [58, 18, 118]],  // lavande → violet
  environnement:[[213, 45, 35],  [255, 200, 45], [25, 150, 70]],   // rouge → jaune → vert
  transport:    [[220, 248, 252], [0, 168, 190],  [0, 78, 100]],   // ciel → teal foncé
  securite:     [[213, 45, 35],  [255, 200, 45], [25, 150, 70]],   // même RdYlGn
};

function lerpStops(stops: Array<[number, number, number]>, t: number): [number, number, number] {
  const s = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(Math.floor(s), stops.length - 2);
  const f = s - i;
  const [r0, g0, b0] = stops[i], [r1, g1, b1] = stops[i + 1];
  return [Math.round(r0 + (r1 - r0) * f), Math.round(g0 + (g1 - g0) * f), Math.round(b0 + (b1 - b0) * f)];
}

const getColorForValue = (v: number, min: number, max: number, hib: boolean, category = "logement"): number[] => {
  const t = Math.max(0, Math.min(1, (v - min) / (max - min || 1)));
  const [r, g, b] = lerpStops(PALETTES[category] ?? PALETTES.logement, hib ? t : 1 - t);
  return [r, g, b, 220];
};

const fmtN = (v: number, dec = 0) =>
  Number.isNaN(v) ? "—" : new Intl.NumberFormat("fr-FR", { maximumFractionDigits: dec }).format(v);

// ─── Composant principal ──────────────────────────────────────────────────────

const Explorateur: React.FC = () => {
  const [selectedCategory, setSelectedCategory] = useState<Category>("logement");
  const [selectedIndicator, setSelectedIndicator] = useState<IndicatorId>("prixM2");
  const [selectedYear, setSelectedYear]           = useState<number>(2024);
  const [hoveredArr, setHoveredArr]               = useState<number | null>(null);
  const [selectedArr, setSelectedArr]             = useState<number | null>(null);
  const [geoData, setGeoData]                     = useState<any>(null);
  const [loadError, setLoadError]                 = useState<string | null>(null);
  const [comparedArrs, setComparedArrs]           = useState<number[]>([1, 11, 20]);
  const [showArrPicker, setShowArrPicker]         = useState(false);

  const [viewState, setViewState] = useState({
    longitude: 2.3522, latitude: 48.8566, zoom: 11.5, pitch: 0, bearing: 0,
  });

  // Charge le GeoJSON enrichi
  useEffect(() => {
    fetch(`${API_BASE}/geo/arrondissements`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setGeoData)
      .catch(() => setLoadError("Données indisponibles — vérifiez que les conteneurs Docker tournent."));
  }, []);

  // Quand on change de catégorie, on sélectionne le premier indicateur de la catégorie
  const handleCategoryChange = (cat: Category) => {
    setSelectedCategory(cat);
    const first = INDICATORS.find((i) => i.category === cat);
    if (first) setSelectedIndicator(first.id);
  };

  const indicatorMeta = useMemo(() => INDICATORS.find((i) => i.id === selectedIndicator), [selectedIndicator]);

  const urbanDataByArr = useMemo(() => {
    const map = new Map<number, UrbanDataItem>();
    if (!geoData) return map;
    for (const feat of geoData.features) {
      const p = feat.properties || {};
      const arr = p.NUM_ARR;
      if (!arr) continue;
      const rd = (id: IndicatorId) => {
        const v = p[propertyKeyFor(id, selectedYear)];
        return typeof v === "number" ? v : NaN;
      };
      map.set(arr, {
        arrondissement: arr,
        nom: p.NOM || arrLabel(arr),
        prixM2: rd("prixM2"), variationPct: rd("variationPct"),
        population: rd("population"), densitePopulation: rd("densitePopulation"),
        indiceQualiteAir: rd("indiceQualiteAir"), nbEspacesVerts: rd("nbEspacesVerts"),
        nbStationsMetro: rd("nbStationsMetro"), nbStationsVelib: rd("nbStationsVelib"),
        tauxCriminalite: rd("tauxCriminalite"),
      });
    }
    return map;
  }, [geoData, selectedYear]);

  const { min, max } = useMemo(() => {
    const vals = [...urbanDataByArr.values()].map((d) => d[selectedIndicator]).filter((v) => !Number.isNaN(v));
    return vals.length ? { min: Math.min(...vals), max: Math.max(...vals) } : { min: 0, max: 1 };
  }, [selectedIndicator, urbanDataByArr]);

  // KPIs Paris entier
  const kpis = useMemo(() => {
    const all = [...urbanDataByArr.values()];
    const avg = (a: number[]) => a.length ? a.reduce((s, v) => s + v, 0) / a.length : NaN;
    const prices = all.map((d) => d.prixM2).filter((v) => !Number.isNaN(v) && v > 0);
    const vars   = all.map((d) => d.variationPct).filter((v) => !Number.isNaN(v));
    const metro  = all.map((d) => d.nbStationsMetro).filter((v) => !Number.isNaN(v));
    const pop    = all.map((d) => d.population).filter((v) => !Number.isNaN(v) && v > 0);
    return {
      avgPrice: avg(prices),
      avgVar:   avg(vars),
      totalMetro: metro.reduce((s, v) => s + v, 0),
      totalPop: pop.reduce((s, v) => s + v, 0),
    };
  }, [urbanDataByArr]);

  // Données série temporelle
  const comparedArrNames = useMemo(() => {
    if (!geoData) return [];
    return comparedArrs.map((n) => {
      const f = geoData.features?.find((feat: any) => feat.properties?.NUM_ARR === n);
      return f?.properties?.NOM || arrLabel(n);
    });
  }, [geoData, comparedArrs]);

  const timeSeriesData = useMemo(() => {
    if (!geoData || !indicatorMeta?.hasYearDimension) return [];
    const field = GOLD_FIELD[selectedIndicator];
    return AVAILABLE_YEARS.map((year) => {
      const point: { year: number; [k: string]: number | string } = { year };
      comparedArrs.forEach((num, idx) => {
        const f = geoData.features?.find((feat: any) => feat.properties?.NUM_ARR === num);
        if (!f) return;
        const v = f.properties?.[`value_${field}_${year}`];
        if (typeof v === "number") point[comparedArrNames[idx] || arrLabel(num)] = v;
      });
      return point;
    });
  }, [geoData, comparedArrs, comparedArrNames, selectedIndicator, indicatorMeta]);

  const chartData = useMemo(
    () => [...urbanDataByArr.values()]
      .sort((a, b) => a.arrondissement - b.arrondissement)
      .map((d) => ({ nom: d.nom, [selectedIndicator]: d[selectedIndicator] })),
    [urbanDataByArr, selectedIndicator]
  );

  const layers = useMemo(() => geoData ? [
    new GeoJsonLayer({
      id: "arrondissements",
      data: geoData,
      filled: true,
      extruded: false,
      getFillColor: (f: any) => {
        const v = f.properties?.[propertyKeyFor(selectedIndicator, selectedYear)];
        return getColorForValue(typeof v === "number" ? v : 0, min, max, indicatorMeta?.higherIsBetter ?? true, indicatorMeta?.category) as unknown as [number, number, number, number];
      },
      getLineColor: [200, 185, 165, 255],
      getLineWidth: 20,
      lineWidthMinPixels: 1,
      lineWidthMaxPixels: 2,
      pickable: true,
      autoHighlight: true,
      highlightColor: [193, 80, 45, 80],
      onHover: (info: any) => setHoveredArr(info.object?.properties?.NUM_ARR ?? null),
      onClick: (info: any) => {
        const n = info.object?.properties?.NUM_ARR;
        if (n) setSelectedArr(n === selectedArr ? null : n);
      },
      updateTriggers: { getFillColor: [selectedIndicator, selectedYear, min, max] },
    }),
  ] : [], [geoData, selectedIndicator, selectedYear, min, max, indicatorMeta, selectedArr]);

  const displayData = (hoveredArr && urbanDataByArr.get(hoveredArr)) || (selectedArr && urbanDataByArr.get(selectedArr)) || undefined;

  const toggleComparison = (n: number) =>
    setComparedArrs((prev) =>
      prev.includes(n) ? prev.filter((x) => x !== n) : prev.length < 6 ? [...prev, n] : prev
    );

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-cream text-ink flex flex-col">

      {/* ── Barre catégories ──────────────────────────────────────────── */}
      <div className="bg-white border-b border-hairline px-4 sticky top-14 z-10">
        <div className="flex items-center gap-1 overflow-x-auto">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => handleCategoryChange(cat.id)}
              className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                selectedCategory === cat.id
                  ? "border-terracotta text-terracotta"
                  : "border-transparent text-ink/50 hover:text-ink hover:border-ink/20"
              }`}
            >
              {cat.icon}
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Barre indicateur + année ──────────────────────────────────── */}
      <div className="bg-cream-dark border-b border-hairline px-4 py-2 flex flex-wrap items-center gap-2">
        <div className="flex gap-1.5 flex-wrap">
          {INDICATORS.filter((i) => i.category === selectedCategory).map((ind) => (
            <button
              key={ind.id}
              onClick={() => setSelectedIndicator(ind.id)}
              className={`px-3 py-1 text-xs rounded-full border transition-all font-medium ${
                selectedIndicator === ind.id
                  ? "text-white border-transparent"
                  : "text-ink/60 border-hairline hover:border-ink/40 bg-white"
              }`}
              style={selectedIndicator === ind.id ? { backgroundColor: ind.color, borderColor: ind.color } : undefined}
            >
              {ind.label}
            </button>
          ))}
        </div>

        {indicatorMeta?.hasYearDimension && (
          <div className="ml-auto flex items-center gap-1.5">
            <span className="text-xs text-ink/40">Année</span>
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              className="bg-white border border-hairline text-ink text-xs rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-terracotta"
            >
              {AVAILABLE_YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        )}

        <span className="font-mono-data text-xs text-ink/30 hidden lg:block ml-2">
          {fmtN(min)} – {fmtN(max)} {indicatorMeta?.unit}
        </span>
      </div>

      {loadError && (
        <div className="px-4 pt-3">
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">{loadError}</div>
        </div>
      )}

      <main className="flex-1 flex flex-col gap-0">

        {/* ── KPI cards ─────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-hairline border-b border-hairline">
          {[
            { icon: <BarChart2 size={16} className="text-terracotta" />, label: "Prix moyen Paris",     value: Number.isNaN(kpis.avgPrice) ? "—" : `${fmtN(kpis.avgPrice)} €/m²`, sub: String(selectedYear) },
            { icon: <TrendingUp size={16} className="text-verdigris" />,  label: "Variation moy.",      value: Number.isNaN(kpis.avgVar)   ? "—" : `${kpis.avgVar >= 0 ? "+" : ""}${kpis.avgVar.toFixed(1)} %`, color: Number.isNaN(kpis.avgVar) ? undefined : kpis.avgVar >= 0 ? "#4F7A6F" : "#C1502D" },
            { icon: <Train size={16} className="text-sky-600" />,         label: "Stations Métro/RER",  value: kpis.totalMetro === 0 ? "—" : fmtN(kpis.totalMetro), sub: "RATP" },
            { icon: <Users size={16} className="text-terracotta" />,      label: "Population Paris",    value: kpis.totalPop === 0 ? "—" : new Intl.NumberFormat("fr-FR", { notation: "compact" }).format(kpis.totalPop), sub: "INSEE 2021" },
          ].map((kpi, i) => (
            <div key={i} className="bg-white px-4 py-3 flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-cream flex-shrink-0 flex items-center justify-center">{kpi.icon}</div>
              <div className="min-w-0">
                <div className="text-ink/40 text-xs truncate">{kpi.label}</div>
                <div className="font-mono-data text-base font-bold leading-tight" style={kpi.color ? { color: kpi.color } : undefined}>{kpi.value}</div>
                {kpi.sub && <div className="text-ink/25 text-xs">{kpi.sub}</div>}
              </div>
            </div>
          ))}
        </div>

        {/* ── Carte + Sidebar ───────────────────────────────────────────── */}
        <div className="flex flex-col lg:flex-row flex-1">
          <section className="flex-1 min-w-0">
            <ParisMaps
              geoData={geoData}
              viewState={viewState}
              min={min} max={max}
              indicatorMeta={indicatorMeta}
              layers={layers}
              propertyKey={propertyKeyFor(selectedIndicator, selectedYear)}
              setViewState={setViewState}
              getColorForValue={getColorForValue}
            />
          </section>
          <Sidebar_details
            INDICATORS_BY_CATEGORY={INDICATORS_BY_CATEGORY}
            displayData={displayData}
            selectedArr={selectedArr}
            selectedIndicator={selectedIndicator}
            indicatorMeta={indicatorMeta}
          />
        </div>

        {/* ── Section graphiques ────────────────────────────────────────── */}
        <div className="border-t border-hairline bg-cream-dark">
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="font-display text-sm font-semibold text-ink">Comparaison & évolution</span>

            {/* Sélecteur arrondissements pour la série temporelle */}
            {indicatorMeta?.hasYearDimension && (
              <div className="relative flex items-center gap-2">
                {/* Chips arrondissements sélectionnés */}
                <div className="flex gap-1 flex-wrap">
                  {comparedArrs.map((n, idx) => (
                    <span
                      key={n}
                      className="flex items-center gap-1 px-2 py-0.5 text-xs rounded-full text-white font-medium"
                      style={{ backgroundColor: ARR_COLORS[idx] }}
                    >
                      {arrLabel(n)}
                      <button onClick={() => toggleComparison(n)} className="opacity-70 hover:opacity-100">
                        <X size={10} />
                      </button>
                    </span>
                  ))}
                </div>

                {/* Bouton ajout arrondissement */}
                {comparedArrs.length < 6 && (
                  <div className="relative">
                    <button
                      onClick={() => setShowArrPicker((p) => !p)}
                      className="flex items-center gap-1 px-2.5 py-1 text-xs border border-hairline rounded-full bg-white text-ink/60 hover:border-ink/40"
                    >
                      + Arrondissement <ChevronDown size={10} />
                    </button>
                    {showArrPicker && (
                      <div className="absolute right-0 top-7 z-20 bg-white border border-hairline rounded-xl shadow-lg p-2 grid grid-cols-5 gap-1 w-52">
                        {Array.from({ length: 20 }, (_, i) => i + 1)
                          .filter((n) => !comparedArrs.includes(n))
                          .map((n) => (
                            <button
                              key={n}
                              onClick={() => { toggleComparison(n); setShowArrPicker(false); }}
                              className="px-1.5 py-1 text-xs rounded-lg border border-hairline hover:bg-cream-dark text-center"
                            >
                              {arrLabel(n)}
                            </button>
                          ))}
                        {Array.from({ length: 20 }, (_, i) => i + 1).every((n) => comparedArrs.includes(n)) && (
                          <span className="col-span-5 text-xs text-ink/40 text-center py-2">Max 6 sélectionnés</span>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="px-4 pb-4">
            <Graphics
              chartData={chartData}
              timeSeriesData={timeSeriesData}
              comparedArrNames={comparedArrNames}
              selectedIndicator={selectedIndicator}
              indicatorMeta={indicatorMeta}
            />
          </div>
        </div>
      </main>
    </div>
  );
};

export default Explorateur;
