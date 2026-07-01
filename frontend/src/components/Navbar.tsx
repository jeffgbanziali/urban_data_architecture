import React, { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { Sun, Moon } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useThemeContext } from "../context/ThemeContext";

const roleLabel: Record<string, string> = {
  client: "Mon espace",
  employe: "Espace employé",
  admin: "Administration",
};

const Navbar: React.FC = () => {
  const { user, logout } = useAuth();
  const { isDark, toggle } = useThemeContext();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const linkStyle = (isActive: boolean): React.CSSProperties => ({
    padding: "6px 12px",
    fontSize: "0.875rem",
    fontWeight: 500,
    transition: "color 0.15s",
    color: isActive ? "#E3522A" : "var(--text-2)",
  });

  return (
    <header
      className="sticky top-0 z-50 backdrop-blur-sm"
      style={{ backgroundColor: "color-mix(in srgb, var(--surface) 95%, transparent)", borderBottom: "1px solid var(--border)" }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between h-14">
        <Link
          to="/"
          className="font-display uppercase tracking-widest text-sm font-bold transition-colors"
          style={{ color: "var(--text)" }}
        >
          Urban Immo
        </Link>

        <nav className="hidden md:flex items-center gap-0.5">
          <NavLink to="/" end style={({ isActive }) => linkStyle(isActive)}>Atlas urbain</NavLink>
          <NavLink to="/biens" style={({ isActive }) => linkStyle(isActive)}>Biens</NavLink>
          {user && (
            <NavLink to="/espace" style={({ isActive }) => linkStyle(isActive)}>
              {roleLabel[user.role] ?? "Mon espace"}
            </NavLink>
          )}
        </nav>

        <div className="hidden md:flex items-center gap-3">
          {/* Toggle dark/light */}
          <button
            onClick={toggle}
            className="flex items-center justify-center w-8 h-8 rounded-lg border transition-all"
            style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-alt)", color: "var(--text-2)" }}
            title={isDark ? "Mode clair" : "Mode sombre"}
          >
            {isDark ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          {user ? (
            <>
              <span className="text-xs font-mono-data" style={{ color: "var(--text-3)" }}>
                {user.full_name.split(" ")[0]}
              </span>
              <button
                onClick={handleLogout}
                className="px-4 py-1.5 text-xs font-semibold rounded-full border transition-colors"
                style={{ borderColor: "var(--border)", color: "var(--text-2)" }}
              >
                Déconnexion
              </button>
            </>
          ) : (
            <>
              <Link
                to="/connexion"
                className="px-3 py-1.5 text-sm font-medium transition-colors"
                style={{ color: "var(--text-2)" }}
              >
                Connexion
              </Link>
              <Link
                to="/inscription"
                className="px-4 py-1.5 text-sm font-semibold rounded-full text-white transition-colors"
                style={{ backgroundColor: "#E3522A" }}
              >
                Créer un compte
              </Link>
            </>
          )}
        </div>

        {/* Mobile menu button */}
        <button
          className="md:hidden p-2 transition-colors"
          style={{ color: "var(--text-2)" }}
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
        <div className="md:hidden px-4 py-3 flex flex-col gap-1" style={{ borderTop: "1px solid var(--border)", backgroundColor: "var(--surface)" }}>
          <NavLink to="/" end style={({ isActive }) => linkStyle(isActive)} onClick={() => setMenuOpen(false)}>Atlas urbain</NavLink>
          <NavLink to="/biens" style={({ isActive }) => linkStyle(isActive)} onClick={() => setMenuOpen(false)}>Biens</NavLink>
          {user ? (
            <>
              <NavLink to="/espace" style={({ isActive }) => linkStyle(isActive)} onClick={() => setMenuOpen(false)}>
                {roleLabel[user.role] ?? "Mon espace"}
              </NavLink>
              <button onClick={handleLogout} className="text-left px-3 py-2 text-sm" style={{ color: "var(--text-3)" }}>
                Déconnexion
              </button>
            </>
          ) : (
            <>
              <NavLink to="/connexion" style={({ isActive }) => linkStyle(isActive)} onClick={() => setMenuOpen(false)}>Connexion</NavLink>
              <NavLink to="/inscription" style={({ isActive }) => linkStyle(isActive)} onClick={() => setMenuOpen(false)}>Créer un compte</NavLink>
            </>
          )}
        </div>
      )}
    </header>
  );
};

export default Navbar;
