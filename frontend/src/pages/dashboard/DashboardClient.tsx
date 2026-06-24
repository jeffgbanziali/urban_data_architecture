// src/pages/dashboard/DashboardClient.tsx
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { api, type Bien, type PrixArrondissement } from "../../lib/api";
import PropertyCard from "../../components/PropertyCard";

const fmt = (n: number) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(n);

const DashboardClient: React.FC = () => {
  const { user } = useAuth();
  const [favoris, setFavoris] = useState<Bien[]>([]);
  const [prixParArr, setPrixParArr] = useState<Map<number, PrixArrondissement>>(new Map());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<Bien[]>("/favoris")
      .then(async (favs) => {
        setFavoris(favs);
        const arrondissements = [...new Set(favs.map((f) => f.arrondissement))];
        const results = await Promise.all(
          arrondissements.map((arr) =>
            api.get<PrixArrondissement[]>(`/prix?annee=2024`).then((rows) => rows.find((r) => r.arrondissement === arr))
          )
        );
        const map = new Map<number, PrixArrondissement>();
        results.forEach((r) => r && map.set(r.arrondissement, r));
        setPrixParArr(map);
      })
      .finally(() => setLoading(false));
  }, []);

  const removeFavori = async (bienId: number) => {
    await api.delete(`/favoris/${bienId}`);
    setFavoris((prev) => prev.filter((b) => b.id !== bienId));
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <h1 className="font-display uppercase text-2xl text-ink font-semibold mb-1">
        Bienvenue, {user?.full_name}
      </h1>
      <p className="text-ink/60 mb-8">Voici vos biens favoris et les tendances de prix associées.</p>

      {loading ? (
        <div className="text-ink/50">Chargement…</div>
      ) : favoris.length === 0 ? (
        <div className="bg-cream-dark border border-hairline rounded-xl p-8 text-center text-ink/60">
          Vous n'avez pas encore de favoris.{" "}
          <Link to="/biens" className="text-terracotta font-semibold">Parcourir les biens</Link>
        </div>
      ) : (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
            {favoris.map((b) => (
              <PropertyCard
                key={b.id}
                bien={b}
                actions={
                  <button
                    onClick={() => removeFavori(b.id)}
                    className="text-xs font-semibold px-3 py-1.5 rounded-full border border-terracotta text-terracotta hover:bg-terracotta hover:text-white transition-colors"
                  >
                    Retirer
                  </button>
                }
              />
            ))}
          </div>

          <h2 className="font-display text-ink font-semibold text-lg mb-4">
            Tendances dans vos arrondissements favoris
          </h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...new Set(favoris.map((f) => f.arrondissement))].map((arr) => {
              const data = prixParArr.get(arr);
              return (
                <div key={arr} className="bg-white border border-hairline rounded-xl p-4">
                  <div className="font-display text-ink font-semibold">{arr}e arrondissement</div>
                  {data ? (
                    <>
                      <div className="font-mono-data text-2xl text-terracotta font-bold mt-1">
                        {fmt(data.prix_m2_median)} €/m²
                      </div>
                      {data.variation_pct != null && (
                        <div className={`text-sm mt-1 ${data.variation_pct > 0 ? "text-terracotta" : "text-verdigris"}`}>
                          {data.variation_pct > 0 ? "+" : ""}{data.variation_pct}% sur un an
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-ink/40 text-sm mt-1">Donnée indisponible</div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};

export default DashboardClient;
