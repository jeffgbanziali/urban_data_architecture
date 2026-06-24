// src/components/ProtectedRoute.tsx
// Protège une route selon l'état d'authentification et, optionnellement,
// une liste de rôles autorisés. Affiche un état de chargement pendant la
// vérification initiale du token (évite un flash de redirection erronée).
import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { Role } from "../lib/api";

interface Props {
  allowedRoles?: Role[];
  children: React.ReactNode;
}

const ProtectedRoute: React.FC<Props> = ({ allowedRoles, children }) => {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh] text-ink">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-terracotta" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/connexion" state={{ from: location }} replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/espace" replace />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
