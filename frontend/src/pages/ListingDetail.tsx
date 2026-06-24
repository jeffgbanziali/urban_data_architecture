// src/pages/ListingDetail.tsx
import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Bien, type PrixArrondissement } from "../lib/api";
import { useAuth } from "../context/AuthContext";

const fmt = (n: number) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(n);

const ListingDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [bien, setBien] = useState<Bien | null>(null);
  const [timeline, setTimeline] = useState<PrixArrondissement[]>([]);
  const [isFavori, setIsFavori] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.get<Bien>(`/biens/${id}`).then(setBien).catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (!bien) return;
    api.get<PrixArrondissement[]>(`/timeline?arr=${bien.arrondissement}`).then(setTimeline).catch(() => {});
  }, [bien]);

  useEffect(() => {
    if (user?.role === "client" && bien) {
      api.get<Bien[]>("/favoris").then((favs) => setIsFavori(favs.some((f) => f.id === bien.id))).catch(() => {});
    }
  }, [user, bien]);

  const toggleFavori = async () => {
    if (!bien) return;
    if (isFavori) {
      await api.delete(`/favoris/${bien.id}`);
    } else {
      await api.post(`/favoris/${bien.id}`);
    }
    setIsFavori(!isFavori);
  };

  if (error) return <div className="max-w-3xl mx-auto px-6 py-16 text-terracotta">Erreur : {error}</div>;
  if (!bien) return <div className="max-w-3xl mx-auto px-6 py-16 text-ink/50">Chargement…</div>;

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <Link to="/biens" className="text-sm text-ink/60 hover:text-terracotta">← Retour aux biens</Link>

      <div className="grid md:grid-cols-2 gap-10 mt-6">
        <div className="h-72 bg-cream-dark rounded-xl flex items-center justify-center text-ink/30 font-display uppercase">
          {bien.photo_url ? (
            <img src={bien.photo_url} alt={bien.titre} className="w-full h-full object-cover rounded-xl" />
          ) : (
            <span>{bien.type_bien} · {bien.arrondissement}e arr.</span>
          )}
        </div>

        <div>
          <h1 className="font-display text-3xl text-ink font-semibold mb-2">{bien.titre}</h1>
          <p className="text-ink/60 mb-4">
            {bien.arrondissement}e arrondissement · {bien.type_bien} · {bien.surface_m2} m²
          </p>
          <p className="font-mono-data text-3xl text-terracotta font-bold mb-1">{fmt(bien.prix)} €</p>
          <p className="text-ink/50 text-sm mb-6">{fmt(bien.prix / bien.surface_m2)} €/m²</p>

          {bien.description && <p className="text-ink/80 mb-6">{bien.description}</p>}

          {user?.role === "client" && (
            <button
              onClick={toggleFavori}
              className={`px-5 py-2.5 rounded-full font-semibold transition-colors ${
                isFavori ? "bg-terracotta text-white" : "border border-ink text-ink hover:bg-ink hover:text-cream"
              }`}
            >
              {isFavori ? "★ Retirer des favoris" : "☆ Ajouter aux favoris"}
            </button>
          )}

          {!user && (
            <p className="text-sm text-ink/50">
              <Link to="/connexion" className="text-terracotta font-semibold">Connectez-vous</Link> en tant que client pour ajouter ce bien à vos favoris.
            </p>
          )}
        </div>
      </div>

      {timeline.length > 0 && (
        <div className="mt-12 bg-cream-dark border border-hairline rounded-xl p-6">
          <h2 className="font-display text-ink font-semibold mb-4">
            Évolution du prix médian dans le {bien.arrondissement}e arrondissement
          </h2>
          <div className="flex items-end gap-3 h-32">
            {timeline.map((p) => {
              const maxVal = Math.max(...timeline.map((t) => t.prix_m2_median));
              const heightPct = (p.prix_m2_median / maxVal) * 100;
              return (
                <div key={p.annee} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className="w-full bg-terracotta/70 rounded-t"
                    style={{ height: `${heightPct}%` }}
                    title={`${fmt(p.prix_m2_median)} €/m²`}
                  />
                  <span className="text-xs text-ink/60">{p.annee}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default ListingDetail;
