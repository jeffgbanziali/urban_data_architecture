// src/components/Navbar.tsx
import React, { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const roleLabel: Record<string, string> = {
  client: "Mon espace",
  employe: "Espace employé",
  admin: "Administration",
};

const Navbar: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 text-sm font-medium transition-colors ${
      isActive ? "text-terracotta" : "text-ink/70 hover:text-ink"
    }`;

  return (
    <header className="bg-cream/95 backdrop-blur-sm border-b border-hairline sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between h-14">
        <Link
          to="/"
          className="font-display uppercase tracking-widest text-ink text-sm font-bold hover:text-terracotta transition-colors"
        >
          Urban Immo
        </Link>

        <nav className="hidden md:flex items-center gap-0.5">
          <NavLink to="/" end className={linkClass}>Atlas urbain</NavLink>
          <NavLink to="/biens" className={linkClass}>Biens</NavLink>
          {user && (
            <NavLink to="/espace" className={linkClass}>
              {roleLabel[user.role] ?? "Mon espace"}
            </NavLink>
          )}
        </nav>

        <div className="hidden md:flex items-center gap-3">
          {user ? (
            <>
              <span className="text-xs text-ink/50 font-mono-data">
                {user.full_name.split(" ")[0]}
              </span>
              <button
                onClick={handleLogout}
                className="px-4 py-1.5 text-xs font-semibold rounded-full border border-ink/30 text-ink/70 hover:border-ink hover:text-ink transition-colors"
              >
                Déconnexion
              </button>
            </>
          ) : (
            <>
              <Link
                to="/connexion"
                className="px-3 py-1.5 text-sm font-medium text-ink/70 hover:text-ink transition-colors"
              >
                Connexion
              </Link>
              <Link
                to="/inscription"
                className="px-4 py-1.5 text-sm font-semibold rounded-full bg-terracotta text-white hover:bg-terracotta-light transition-colors"
              >
                Créer un compte
              </Link>
            </>
          )}
        </div>

        <button
          className="md:hidden p-2 text-ink/70"
          onClick={() => setMenuOpen((o) => !o)}
          aria-label="Menu"
          aria-expanded={menuOpen}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            {menuOpen
              ? <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" />
              : <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />}
          </svg>
        </button>
      </div>

      {menuOpen && (
        <div className="md:hidden border-t border-hairline bg-cream px-4 py-3 flex flex-col gap-1">
          <NavLink to="/" end className={linkClass} onClick={() => setMenuOpen(false)}>Atlas urbain</NavLink>
          <NavLink to="/biens" className={linkClass} onClick={() => setMenuOpen(false)}>Biens</NavLink>
          {user ? (
            <>
              <NavLink to="/espace" className={linkClass} onClick={() => setMenuOpen(false)}>
                {roleLabel[user.role] ?? "Mon espace"}
              </NavLink>
              <button onClick={handleLogout} className="text-left px-3 py-2 text-sm text-ink/60">
                Déconnexion
              </button>
            </>
          ) : (
            <>
              <NavLink to="/connexion" className={linkClass} onClick={() => setMenuOpen(false)}>Connexion</NavLink>
              <NavLink to="/inscription" className={linkClass} onClick={() => setMenuOpen(false)}>Créer un compte</NavLink>
            </>
          )}
        </div>
      )}
    </header>
  );
};

export default Navbar;
