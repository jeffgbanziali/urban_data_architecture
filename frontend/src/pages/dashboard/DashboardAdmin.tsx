// src/pages/dashboard/DashboardAdmin.tsx
import React, { useState } from "react";
import { useAuth } from "../../context/AuthContext";
import BienManager from "./BienManager";
import UserManager from "./UserManager";

const TABS = [
  { id: "users", label: "Utilisateurs" },
  { id: "biens", label: "Biens" },
  { id: "systeme", label: "Supervision technique" },
] as const;

const DashboardAdmin: React.FC = () => {
  const { user } = useAuth();
  const [tab, setTab] = useState<typeof TABS[number]["id"]>("users");

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <h1 className="font-display uppercase text-2xl text-ink font-semibold mb-1">
        Espace administrateur — {user?.full_name}
      </h1>
      <p className="text-ink/60 mb-8">Pilotage des comptes, du portefeuille de biens et de la chaîne de données.</p>

      <div className="flex gap-2 mb-8 border-b border-hairline">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition-colors ${
              tab === t.id ? "border-terracotta text-terracotta" : "border-transparent text-ink/60 hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "users" && <UserManager />}
      {tab === "biens" && <BienManager canDelete />}
      {tab === "systeme" && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: "Documentation API (Swagger)", href: "http://localhost:8000/docs" },
            { label: "Console MinIO (data lake)", href: "http://localhost:9001" },
            { label: "Interface Airflow (orchestration)", href: "http://localhost:8080" },
            { label: "Documentation du projet", href: "/docs.html" },
          ].map((link) => (
            <a
              key={link.label}
              href={link.href}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-white border border-hairline rounded-xl p-5 hover:border-terracotta transition-colors"
            >
              <div className="font-display text-ink font-semibold mb-1">{link.label}</div>
              <div className="text-xs text-ink/50">{link.href}</div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
};

export default DashboardAdmin;
