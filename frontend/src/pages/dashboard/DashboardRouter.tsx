// src/pages/dashboard/DashboardRouter.tsx
import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

const DashboardRouter: React.FC = () => {
  const { user } = useAuth();
  if (!user) return null; // ProtectedRoute gère déjà la redirection si non connecté

  switch (user.role) {
    case "admin":
      return <Navigate to="/espace/admin" replace />;
    case "employe":
      return <Navigate to="/espace/employe" replace />;
    default:
      return <Navigate to="/espace/client" replace />;
  }
};

export default DashboardRouter;
