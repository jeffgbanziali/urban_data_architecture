// src/pages/Login.tsx
import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";

const Login: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const from = (location.state as { from?: Location })?.from?.pathname;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate(from || "/espace", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Connexion impossible.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto px-6 py-16">
      <h1 className="font-display uppercase text-2xl text-ink font-semibold mb-2">Connexion</h1>
      <p className="text-ink/60 mb-8">Accédez à votre espace client, employé ou administrateur.</p>

      <form onSubmit={handleSubmit} className="space-y-4 bg-white border border-hairline rounded-xl p-6 shadow-sm">
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
          <span className="text-sm text-ink/70">Mot de passe</span>
          <input
            type="password"
            required
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
          {loading ? "Connexion…" : "Se connecter"}
        </button>
      </form>

      <p className="text-sm text-ink/60 mt-6 text-center">
        Pas encore de compte ? <Link to="/inscription" className="text-terracotta font-semibold">Inscrivez-vous</Link>
      </p>

      
    </div>
  );
};

export default Login;
