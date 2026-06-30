import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Legend,
} from "recharts";

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
  hasYearDimension?: boolean;
}

interface ChartDataItem {
  nom: string;
  [key: string]: number | string;
}

interface TimeSeriesItem {
  year: number;
  [key: string]: number | string;
}

const LINE_COLORS = [
  "#C1502D", // terracotta
  "#1C2E4A", // ink
  "#4F7A6F", // verdigris
  "#f97316", // orange
  "#7c3aed", // violet
  "#16a34a", // green
  "#0284c7", // sky
  "#db2777", // pink
];

const TOOLTIP_STYLE = {
  backgroundColor: "#1C2E4A",
  border: "none",
  borderRadius: "8px",
  color: "#F6F1E7",
  fontSize: "12px",
};

const TICK_STYLE = { fontSize: 10, fill: "#1C2E4A" };

type Props = {
  chartData: ChartDataItem[];
  timeSeriesData: TimeSeriesItem[];
  comparedArrNames: string[];
  selectedIndicator: IndicatorId;
  indicatorMeta: IndicatorMeta | undefined;
};

function fmtVal(v: number | undefined, unit: string): string {
  if (v == null || Number.isNaN(v)) return "—";
  const n = new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: unit === "%" ? 1 : 0,
    notation: Math.abs(v) >= 10000 ? "compact" : "standard",
  }).format(v);
  return unit ? `${n} ${unit}` : n;
}

const Graphics = ({
  chartData,
  timeSeriesData,
  comparedArrNames,
  selectedIndicator,
  indicatorMeta,
}: Props) => {
  const unit = indicatorMeta?.unit ?? "";

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      {/* Comparaison barres — tous les arrondissements pour l'année sélectionnée */}
      <div className="bg-white border border-hairline rounded-xl p-5 shadow-sm">
        <h3 className="font-display text-sm font-semibold text-ink mb-4">
          Comparaison · {indicatorMeta?.label}
        </h3>
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: 8, bottom: 56 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#DED5C2" vertical={false} />
              <XAxis
                dataKey="nom"
                angle={-45}
                textAnchor="end"
                height={56}
                tick={TICK_STYLE}
              />
              <YAxis
                tick={TICK_STYLE}
                width={52}
                tickFormatter={(v) =>
                  new Intl.NumberFormat("fr-FR", { notation: "compact" }).format(v)
                }
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(v: any) => [fmtVal(v, unit), indicatorMeta?.label ?? ""]}
                labelFormatter={(l) => String(l)}
              />
              <Bar
                dataKey={selectedIndicator}
                fill={indicatorMeta?.color || "#C1502D"}
                radius={[3, 3, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Évolution temporelle multi-arrondissements */}
      <div className="bg-white border border-hairline rounded-xl p-5 shadow-sm">
        <h3 className="font-display text-sm font-semibold text-ink mb-4">
          Évolution 2021 – 2025
          {!indicatorMeta?.hasYearDimension && (
            <span className="ml-2 text-xs font-normal text-ink/40">
              — indicateur sans dimension temporelle
            </span>
          )}
        </h3>
        <div className="h-60">
          {indicatorMeta?.hasYearDimension && comparedArrNames.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={timeSeriesData}
                margin={{ top: 4, right: 8, left: 8, bottom: 4 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#DED5C2" vertical={false} />
                <XAxis dataKey="year" tick={TICK_STYLE} />
                <YAxis
                  tick={TICK_STYLE}
                  width={52}
                  tickFormatter={(v) =>
                    new Intl.NumberFormat("fr-FR", { notation: "compact" }).format(v)
                  }
                />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(v: any, name: any) => [fmtVal(v, unit), String(name ?? "")]}
                />
                <Legend
                  wrapperStyle={{ fontSize: "10px", paddingTop: "4px" }}
                  iconSize={8}
                />
                {comparedArrNames.map((name, i) => (
                  <Line
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={LINE_COLORS[i % LINE_COLORS.length]}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-center px-6">
              <p className="text-ink/30 text-sm leading-relaxed">
                {indicatorMeta?.hasYearDimension
                  ? "Sélectionnez des arrondissements dans le sélecteur ci-dessus pour afficher leur évolution."
                  : "L'évolution temporelle est disponible pour les indicateurs prix immobilier et variation annuelle."}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Graphics;
