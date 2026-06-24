// src/context/AuthContext.tsx
// Fournit l'état d'authentification à toute l'application : utilisateur
// courant, rôle, fonctions login/register/logout. Au chargement, si un token
// est déjà stocké (session précédente), on vérifie sa validité via /auth/me
// plutôt que de faire confiance au contenu local — un compte désactivé par un
// admin doit immédiatement perdre l'accès, même avec un vieux token valide.
import React, { createContext, useContext, useEffect, useState } from "react";
import { api, clearToken, setToken, type AuthResponse, type Role, type UserOut } from "../lib/api";

interface AuthContextValue {
  user: UserOut | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<Role>;
  register: (email: string, password: string, fullName: string) => Promise<Role>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserOut | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    api
      .get<UserOut>("/auth/me")
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const res = await api.post<AuthResponse>("/auth/login", { email, password });
    setToken(res.access_token);
    const me = await api.get<UserOut>("/auth/me");
    setUser(me);
    return res.role;
  };

  const register = async (email: string, password: string, fullName: string) => {
    const res = await api.post<AuthResponse>("/auth/register", { email, password, full_name: fullName });
    setToken(res.access_token);
    const me = await api.get<UserOut>("/auth/me");
    setUser(me);
    return res.role;
  };

  const logout = () => {
    clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé à l'intérieur de <AuthProvider>");
  return ctx;
}
