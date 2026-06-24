// src/pages/dashboard/DashboardEmploye.tsx
import React from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import BienManager from "./BienManager";

const DashboardEmploye: React.FC = () => {
  const { user } = useAuth();

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between flex-wrap gap-4 mb-8">
        <div>
          <h1 className="font-display uppercase text-2xl text-ink font-semibold mb-1">
            Espace employé — {user?.full_name}
          </h1>
          <p className="text-ink/60">Gérez le portefeuille de biens et conseillez vos clients avec les données.</p>
        </div>
        <Link
          to="/explorateur"
          className="px-5 py-2.5 rounded-full bg-ink text-cream font-semibold hover:bg-ink-light transition-colors"
        >
          Ouvrir l'explorateur de données →
        </Link>
      </div>

      <BienManager canDelete={false} />
    </div>
  );
};

export default DashboardEmploye;
