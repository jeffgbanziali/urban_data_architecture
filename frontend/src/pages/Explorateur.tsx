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
  pctLogementsSociaux: number;
  pctAppartements: number;
}

type IndicatorId =
  | "prixM2" | "variationPct"
  | "population" | "densitePopulation"
  | "indiceQualiteAir" | "nbEspacesVerts"
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
  hasYearDimension?: boolean;
}

// ─── Constantes ──────────────────────────────────────────────────────────────

const INDICATORS: IndicatorMeta[] = [
  { id: "prixM2",           label: "Prix immobilier",     unit: "€/m²",         higherIsBetter: false, color: "#DC2626", category: "logement",     hasYearDimension: true },
  { id: "variationPct",     label: "Variation annuelle",  unit: "%",             higherIsBetter: false, color: "#F59E0B", category: "logement",     hasYearDimension: true },
  { id: "pctLogementsSociaux", label: "Logements sociaux",    unit: "%",         higherIsBetter: true,  color: "#1A56DB", category: "logement" },
  { id: "pctAppartements",     label: "Part d'appartements",  unit: "%",         higherIsBetter: true,  color: "#6366F1", category: "logement" },
  { id: "population",       label: "Population",          unit: "hab",           higherIsBetter: true,  color: "#7C3AED", category: "social" },
  { id: "densitePopulation",label: "Densité",             unit: "hab/km²",       higherIsBetter: false, color: "#7C3AED", category: "social" },
  { id: "indiceQualiteAir", label: "Qualité de l'air",    unit: "/100",          higherIsBetter: true,  color: "#10B981", category: "environnement" },
  { id: "nbEspacesVerts",   label: "Espaces verts",       unit: "lieux",         higherIsBetter: true,  color: "#059669", category: "environnement" },
  { id: "nbStationsMetro",  label: "Stations Métro/RER",  unit: "stations",      higherIsBetter: true,  color: "#0EA5E9", category: "transport" },
  { id: "nbStationsVelib",  label: "Stations Vélib",      unit: "stations",      higherIsBetter: true,  color: "#06B6D4", category: "transport" },
  { id: "tauxCriminalite",  label: "Criminalité",         unit: "faits/1000hab", higherIsBetter: false, color: "#DC2626", category: "securite" },
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
  prixM2:               "prixM2",
  variationPct:         "variationPct",
  population:           "population",
  densitePopulation:    "densite_hab_km2",
  indiceQualiteAir:     "indice_qualite_air",
  nbEspacesVerts:       "nb_espaces_verts",
  nbStationsMetro:      "nb_stations_metro",
  nbStationsVelib:      "nb_stations_velib",
  tauxCriminalite:      "taux_criminalite",
  pctLogementsSociaux:  "pct_logements_sociaux",
  pctAppartements:      "pct_appartements",
};

const ARR_COLORS = ["#1A56DB", "#E3522A", "#10B981", "#F59E0B", "#7C3AED", "#0EA5E9"];
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

// Palettes 5 paliers par catégorie — spec : vert menthe → ambre → rouge brique
// t=0 = première couleur (valeur "haute/mauvaise" pour hib=false, ou "basse" pour hib=true)
// t=1 = dernière couleur (valeur "basse/bonne" pour hib=false, ou "haute/bonne" pour hib=true)
const PALETTES: Record<string, Array<[number, number, number]>> = {
  logement:     [[220, 38,  38], [249, 115,  22], [245, 158,  11], [ 52, 211, 153], [ 16, 185, 129]],
  social:       [[224, 231, 255], [165, 180, 252], [ 99, 102, 241], [ 79,  70, 229], [ 67,  56, 202]],
  environnement:[[220, 38,  38], [249, 115,  22], [245, 158,  11], [ 52, 211, 153], [ 16, 185, 129]],
  transport:    [[186, 230, 253], [125, 211, 252], [ 14, 165, 233], [  3, 130, 195], [  2, 100, 160]],
  securite:     [[220, 38,  38], [249, 115,  22], [245, 158,  11], [ 52, 211, 153], [ 16, 185, 129]],
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
        pctLogementsSociaux: rd("pctLogementsSociaux"), pctAppartements: rd("pctAppartements"),
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
      getLineColor: [229, 231, 235, 255],
      getLineWidth: 20,
      lineWidthMinPixels: 1,
      lineWidthMaxPixels: 2,
      pickable: true,
      autoHighlight: true,
      highlightColor: [26, 86, 219, 60],
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
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "var(--bg)", color: "var(--text)" }}>

      {/* ── En-tête atlas ────────────────────────────────────────────── */}
      <div className="border-b px-6 py-4 flex items-center justify-between" style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
        <div>
          <h1 className="font-display text-lg font-bold" style={{ color: "var(--text)" }}>
            Atlas immobilier de Paris
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--text-2)" }}>
            20 arrondissements · Données DVF réelles
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium" style={{ color: "var(--text-2)" }}>Année</span>
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              disabled={!indicatorMeta?.hasYearDimension}
              className="border rounded-lg px-2.5 py-1.5 text-sm font-medium focus:outline-none transition disabled:opacity-40"
              style={{ borderColor: "var(--border)", color: "var(--text)", backgroundColor: "var(--surface)" }}
            >
              {AVAILABLE_YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* ── Barre catégories ──────────────────────────────────────────── */}
      <div className="border-b px-4 sticky top-14 z-10" style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
        <div className="flex items-center gap-1 overflow-x-auto">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => handleCategoryChange(cat.id)}
              className="flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
              style={
                selectedCategory === cat.id
                  ? { borderBottomColor: "var(--accent)", color: "var(--accent)" }
                  : { borderBottomColor: "transparent", color: "var(--text-2)" }
              }
            >
              {cat.icon}
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Barre indicateurs ─────────────────────────────────────────── */}
      <div className="border-b px-4 py-2 flex flex-wrap items-center gap-2" style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
        <div className="flex gap-1.5 flex-wrap">
          {INDICATORS.filter((i) => i.category === selectedCategory).map((ind) => (
            <button
              key={ind.id}
              onClick={() => setSelectedIndicator(ind.id)}
              className="px-3 py-1.5 text-xs rounded-full border transition-all font-medium"
              style={
                selectedIndicator === ind.id
                  ? { backgroundColor: "var(--accent)", borderColor: "var(--accent)", color: "#fff" }
                  : { backgroundColor: "var(--surface)", borderColor: "var(--border)", color: "var(--text-2)" }
              }
            >
              {ind.label}
            </button>
          ))}
        </div>
        <span className="font-mono-data text-xs hidden lg:block ml-auto" style={{ color: "var(--text-3)" }}>
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
        <div className="grid grid-cols-2 lg:grid-cols-4 border-b" style={{ gap: "1px", backgroundColor: "var(--border)", borderColor: "var(--border)" }}>
          {[
            { icon: <BarChart2 size={16} style={{ color: "#E3522A" }} />, label: "Prix moyen Paris",    value: Number.isNaN(kpis.avgPrice) ? "—" : `${fmtN(kpis.avgPrice)} €/m²`, sub: String(selectedYear) },
            { icon: <TrendingUp size={16} style={{ color: "#10B981" }} />, label: "Variation moy.",     value: Number.isNaN(kpis.avgVar)   ? "—" : `${kpis.avgVar >= 0 ? "+" : ""}${kpis.avgVar.toFixed(1)} %`, color: Number.isNaN(kpis.avgVar) ? undefined : kpis.avgVar >= 0 ? "#10B981" : "#E3522A" },
            { icon: <Train size={16} style={{ color: "#0EA5E9" }} />,      label: "Stations Métro/RER", value: kpis.totalMetro === 0 ? "—" : fmtN(kpis.totalMetro), sub: "RATP" },
            { icon: <Users size={16} style={{ color: "#E3522A" }} />,      label: "Population Paris",   value: kpis.totalPop === 0 ? "—" : new Intl.NumberFormat("fr-FR", { notation: "compact" }).format(kpis.totalPop), sub: "INSEE 2021" },
          ].map((kpi, i) => (
            <div key={i} className="px-4 py-3 flex items-center gap-3" style={{ backgroundColor: "var(--surface)" }}>
              <div className="w-8 h-8 rounded-lg flex-shrink-0 flex items-center justify-center" style={{ backgroundColor: "var(--surface-alt)" }}>{kpi.icon}</div>
              <div className="min-w-0">
                <div className="text-xs truncate" style={{ color: "var(--text-2)" }}>{kpi.label}</div>
                <div className="font-mono-data text-base font-bold leading-tight" style={kpi.color ? { color: kpi.color } : { color: "var(--text)" }}>{kpi.value}</div>
                {kpi.sub && <div className="text-xs" style={{ color: "var(--text-3)" }}>{kpi.sub}</div>}
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
        <div className="border-t" style={{ borderColor: "var(--border)", backgroundColor: "var(--bg)" }}>
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="font-display text-sm font-semibold" style={{ color: "var(--text)" }}>Comparaison & évolution</span>

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
                      className="flex items-center gap-1 px-2.5 py-1 text-xs border rounded-full transition-colors"
                      style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)", color: "var(--text-2)" }}
                    >
                      + Arrondissement <ChevronDown size={10} />
                    </button>
                    {showArrPicker && (
                      <div className="absolute right-0 top-7 z-20 rounded-xl shadow-lg p-2 grid grid-cols-5 gap-1 w-52" style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}>
                        {Array.from({ length: 20 }, (_, i) => i + 1)
                          .filter((n) => !comparedArrs.includes(n))
                          .map((n) => (
                            <button
                              key={n}
                              onClick={() => { toggleComparison(n); setShowArrPicker(false); }}
                              className="px-1.5 py-1 text-xs rounded-lg text-center transition-colors"
                              style={{ border: "1px solid var(--border)", color: "var(--text-2)", backgroundColor: "var(--surface)" }}
                            >
                              {arrLabel(n)}
                            </button>
                          ))}
                        {Array.from({ length: 20 }, (_, i) => i + 1).every((n) => comparedArrs.includes(n)) && (
                          <span className="col-span-5 text-xs text-center py-2" style={{ color: "var(--text-3)" }}>Max 6 sélectionnés</span>
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
