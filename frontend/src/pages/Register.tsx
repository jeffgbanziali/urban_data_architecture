// src/pages/Register.tsx
import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";

const Register: React.FC = () => {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await register(email, password, fullName);
      navigate("/espace", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Inscription impossible.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto px-6 py-16">
      <h1 className="font-display uppercase text-2xl text-ink font-semibold mb-2">Créer un compte client</h1>
      <p className="text-ink/60 mb-8">
        Suivez vos biens favoris et les tendances de prix de vos arrondissements préférés.
        <br />
        <span className="text-xs text-ink/40">
          (Les comptes employé et administrateur sont créés par un administrateur depuis son espace.)
        </span>
      </p>

      <form onSubmit={handleSubmit} className="space-y-4 bg-white border border-hairline rounded-xl p-6 shadow-sm">
        <label className="block">
          <span className="text-sm text-ink/70">Nom complet</span>
          <input
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
            placeholder="Jeanne Dupont"
          />
        </label>
        <label className="block">
          <span className="text-sm text-ink/70">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
            placeholder="vous@exemple.fr"
          />
        </label>
        <label className="block">
          <span className="text-sm text-ink/70">Mot de passe (6 caractères minimum)</span>
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
            placeholder="••••••••"
          />
        </label>

        {error && <p className="text-sm text-terracotta">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 rounded-full bg-terracotta text-white font-semibold hover:bg-terracotta-light transition-colors disabled:opacity-60"
        >
          {loading ? "Création…" : "Créer mon compte"}
        </button>
      </form>

      <p className="text-sm text-ink/60 mt-6 text-center">
        Déjà inscrit ? <Link to="/connexion" className="text-terracotta font-semibold">Connectez-vous</Link>
      </p>
    </div>
  );
};

export default Register;
