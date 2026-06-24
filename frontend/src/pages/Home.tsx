// src/pages/Home.tsx
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Bien } from "../lib/api";
import PropertyCard from "../components/PropertyCard";

const Home: React.FC = () => {
  const [biens, setBiens] = useState<Bien[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<Bien[]>("/biens?statut=disponible")
      .then((data) => setBiens(data.slice(0, 3)))
      .catch(() => setBiens([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      {/* Hero */}
      <section className="bg-ink text-cream">
        <div className="max-w-screen-2xl mx-auto px-6 py-20 grid md:grid-cols-2 gap-12 items-center">
          <div>
            <p className="font-display uppercase tracking-widest text-terracotta-light text-sm mb-3">
              Agence immobilière · Paris
            </p>
            <h1 className="font-display text-4xl md:text-5xl font-bold leading-tight mb-6">
              Trouvez votre prochain logement,
              <br />guidé par la donnée.
            </h1>
            <p className="text-cream/80 text-lg mb-8 max-w-md">
              Urban Immo combine expertise terrain et analyse data en temps réel
              des 20 arrondissements parisiens : prix au m², qualité de vie,
              tendances — pour acheter ou vendre en toute confiance.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link
                to="/biens"
                className="px-6 py-3 rounded-full bg-terracotta text-white font-semibold hover:bg-terracotta-light transition-colors"
              >
                Voir nos biens
              </Link>
              <Link
                to="/explorateur"
                className="px-6 py-3 rounded-full border border-cream/30 text-cream font-semibold hover:bg-cream/10 transition-colors"
              >
                Explorer les données par quartier
              </Link>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {[
              ["20", "arrondissements analysés"],
              ["4+", "indicateurs par quartier"],
              ["Temps réel", "flux de transactions"],
              ["100%", "transparence des données"],
            ].map(([value, label]) => (
              <div key={label} className="bg-cream/5 border border-cream/15 rounded-xl p-5">
                <div className="font-display text-2xl font-bold text-terracotta-light">{value}</div>
                <div className="text-cream/70 text-sm mt-1">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Biens en vedette */}
      <section className="max-w-screen-2xl mx-auto px-6 py-16">
        <div className="flex items-end justify-between mb-8">
          <div>
            <h2 className="font-display uppercase text-2xl text-ink font-semibold">Biens à la une</h2>
            <p className="text-ink/60 mt-1">Une sélection de nos dernières annonces disponibles.</p>
          </div>
          <Link to="/biens" className="text-terracotta font-semibold hover:underline whitespace-nowrap">
            Voir tous les biens →
          </Link>
        </div>

        {loading ? (
          <div className="text-ink/50">Chargement des biens…</div>
        ) : biens.length === 0 ? (
          <div className="text-ink/50 bg-cream-dark border border-hairline rounded-xl p-8 text-center">
            Aucun bien disponible pour le moment. Vérifiez que l'API et la base de données sont démarrées.
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {biens.map((b) => (
              <PropertyCard key={b.id} bien={b} />
            ))}
          </div>
        )}
      </section>

      {/* Pourquoi nous */}
      <section className="bg-cream-dark border-t border-hairline">
        <div className="max-w-screen-2xl mx-auto px-6 py-16 grid md:grid-cols-3 gap-8">
          {[
            {
              title: "Données vérifiées",
              text: "Nos prix s'appuient sur les transactions DVF et les indicateurs INSEE, nettoyés et mis à jour via notre pipeline data.",
            },
            {
              title: "Accompagnement par profil",
              text: "Espace client pour suivre vos favoris, espace employé pour gérer le portefeuille, espace admin pour piloter les comptes.",
            },
            {
              title: "Vision quartier par quartier",
              text: "Explorez la rose des 20 arrondissements : prix, logements sociaux, qualité de l'air et bien plus.",
            },
          ].map((item) => (
            <div key={item.title}>
              <h3 className="font-display text-ink font-semibold text-lg mb-2">{item.title}</h3>
              <p className="text-ink/70 text-sm">{item.text}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default Home;
