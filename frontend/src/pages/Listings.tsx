// src/pages/Listings.tsx
import React, { useEffect, useState } from "react";
import { api, type Bien } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PropertyCard from "../components/PropertyCard";

const TYPES = ["Studio", "T2", "T3", "T4", "T5+", "Maison"];

const Listings: React.FC = () => {
  const { user } = useAuth();
  const [biens, setBiens] = useState<Bien[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [favoris, setFavoris] = useState<Set<number>>(new Set());

  const [arrondissement, setArrondissement] = useState("");
  const [typeBien, setTypeBien] = useState("");
  const [prixMax, setPrixMax] = useState("");

  const loadBiens = () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (arrondissement) params.set("arrondissement", arrondissement);
    if (typeBien) params.set("type_bien", typeBien);
    if (prixMax) params.set("prix_max", prixMax);

    api
      .get<Bien[]>(`/biens?${params.toString()}`)
      .then(setBiens)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadBiens();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [arrondissement, typeBien, prixMax]);

  useEffect(() => {
    if (user?.role === "client") {
      api
        .get<Bien[]>("/favoris")
        .then((data) => setFavoris(new Set(data.map((b) => b.id))))
        .catch(() => {});
    }
  }, [user]);

  const toggleFavori = async (bienId: number) => {
    if (favoris.has(bienId)) {
      await api.delete(`/favoris/${bienId}`);
      setFavoris((prev) => {
        const next = new Set(prev);
        next.delete(bienId);
        return next;
      });
    } else {
      await api.post(`/favoris/${bienId}`);
      setFavoris((prev) => new Set(prev).add(bienId));
    }
  };

  return (
    <div className="max-w-screen-2xl mx-auto px-6 py-10">
      <h1 className="font-display uppercase text-3xl text-ink font-semibold mb-2">Nos biens</h1>
      <p className="text-ink/60 mb-8">Filtrez par arrondissement, typologie ou budget.</p>

      <div className="flex flex-wrap gap-4 mb-8 bg-cream-dark border border-hairline rounded-xl p-4">
        <label className="flex flex-col gap-1 text-sm text-ink/70">
          Arrondissement
          <select
            value={arrondissement}
            onChange={(e) => setArrondissement(e.target.value)}
            className="rounded-lg border border-hairline px-3 py-1.5 bg-white"
          >
            <option value="">Tous</option>
            {Array.from({ length: 20 }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>{n}e</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm text-ink/70">
          Typologie
          <select
            value={typeBien}
            onChange={(e) => setTypeBien(e.target.value)}
            className="rounded-lg border border-hairline px-3 py-1.5 bg-white"
          >
            <option value="">Toutes</option>
            {TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm text-ink/70">
          Prix maximum (€)
          <input
            type="number"
            min={0}
            placeholder="Sans limite"
            value={prixMax}
            onChange={(e) => setPrixMax(e.target.value)}
            className="rounded-lg border border-hairline px-3 py-1.5 bg-white w-40"
          />
        </label>
      </div>

      {loading ? (
        <div className="text-ink/50">Chargement…</div>
      ) : error ? (
        <div className="text-terracotta">Impossible de charger les biens : {error}</div>
      ) : biens.length === 0 ? (
        <div className="text-ink/50 bg-cream-dark border border-hairline rounded-xl p-8 text-center">
          Aucun bien ne correspond à ces critères.
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {biens.map((b) => (
            <PropertyCard
              key={b.id}
              bien={b}
              actions={
                user?.role === "client" ? (
                  <button
                    onClick={() => toggleFavori(b.id)}
                    className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-colors ${
                      favoris.has(b.id)
                        ? "bg-terracotta text-white border-terracotta"
                        : "border-ink/30 text-ink/70 hover:border-terracotta hover:text-terracotta"
                    }`}
                  >
                    {favoris.has(b.id) ? "★ Favori" : "☆ Ajouter"}
                  </button>
                ) : undefined
              }
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default Listings;
