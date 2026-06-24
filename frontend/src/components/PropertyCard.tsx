// src/components/PropertyCard.tsx
import React from "react";
import { Link } from "react-router-dom";
import type { Bien } from "../lib/api";

const statutLabel: Record<Bien["statut"], { label: string; className: string }> = {
  disponible: { label: "Disponible", className: "bg-verdigris/15 text-verdigris" },
  sous_offre: { label: "Sous offre", className: "bg-terracotta/15 text-terracotta" },
  vendu: { label: "Vendu", className: "bg-ink/10 text-ink/60" },
};

const fmtPrix = (n: number) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(n);

const PropertyCard: React.FC<{ bien: Bien; actions?: React.ReactNode }> = ({ bien, actions }) => {
  const statut = statutLabel[bien.statut];
  return (
    <div className="bg-white border border-hairline rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow flex flex-col">
      <div className="h-44 bg-cream-dark flex items-center justify-center text-ink/30 font-display text-sm uppercase">
        {bien.photo_url ? (
          <img src={bien.photo_url} alt={bien.titre} className="w-full h-full object-cover" />
        ) : (
          <span>{bien.type_bien} · {bien.arrondissement}e arr.</span>
        )}
      </div>
      <div className="p-4 flex flex-col gap-2 flex-1">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-display text-ink text-base leading-tight">{bien.titre}</h3>
          <span className={`text-xs font-semibold px-2 py-1 rounded-full whitespace-nowrap ${statut.className}`}>
            {statut.label}
          </span>
        </div>
        <p className="text-sm text-ink/60">
          {bien.arrondissement}e arrondissement · {bien.type_bien} · {bien.surface_m2} m²
        </p>
        <p className="font-mono-data text-terracotta text-lg font-semibold mt-1">
          {fmtPrix(bien.prix)} €
          <span className="text-xs text-ink/40 ml-1">
            ({fmtPrix(bien.prix / bien.surface_m2)} €/m²)
          </span>
        </p>
        <div className="mt-auto pt-2 flex items-center justify-between gap-2">
          <Link to={`/biens/${bien.id}`} className="text-sm font-semibold text-ink hover:text-terracotta">
            Voir le bien →
          </Link>
          {actions}
        </div>
      </div>
    </div>
  );
};

export default PropertyCard;
