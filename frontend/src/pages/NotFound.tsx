// src/pages/NotFound.tsx
import React from "react";
import { Link } from "react-router-dom";

const NotFound: React.FC = () => (
  <div className="max-w-xl mx-auto px-6 py-24 text-center">
    <p className="font-display text-terracotta text-6xl font-bold mb-4">404</p>
    <h1 className="font-display uppercase text-2xl text-ink font-semibold mb-2">Page introuvable</h1>
    <p className="text-ink/60 mb-8">Cette adresse ne correspond à aucune page d'Urban Immo.</p>
    <Link to="/" className="px-6 py-3 rounded-full bg-terracotta text-white font-semibold hover:bg-terracotta-light">
      Retour à l'accueil
    </Link>
  </div>
);

export default NotFound;
