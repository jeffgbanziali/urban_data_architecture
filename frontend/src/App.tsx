// src/App.tsx
import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import ProtectedRoute from "./components/ProtectedRoute";

import Listings from "./pages/Listings";
import ListingDetail from "./pages/ListingDetail";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Explorateur from "./pages/Explorateur";
import NotFound from "./pages/NotFound";
import DashboardRouter from "./pages/dashboard/DashboardRouter";
import DashboardClient from "./pages/dashboard/DashboardClient";
import DashboardEmploye from "./pages/dashboard/DashboardEmploye";
import DashboardAdmin from "./pages/dashboard/DashboardAdmin";

import "./App.css";

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="min-h-screen flex flex-col bg-cream text-ink">
    <Navbar />
    <main className="flex-1 ">{children}</main>
    <Footer />
  </div>
);

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<Explorateur />} />
            <Route path="/biens" element={<Listings />} />
            <Route path="/biens/:id" element={<ListingDetail />} />
            <Route path="/connexion" element={<Login />} />
            <Route path="/inscription" element={<Register />} />

            <Route
              path="/espace"
              element={
                <ProtectedRoute>
                  <DashboardRouter />
                </ProtectedRoute>
              }
            />
            <Route
              path="/espace/client"
              element={
                <ProtectedRoute allowedRoles={["client"]}>
                  <DashboardClient />
                </ProtectedRoute>
              }
            />
            <Route
              path="/espace/employe"
              element={
                <ProtectedRoute allowedRoles={["employe", "admin"]}>
                  <DashboardEmploye />
                </ProtectedRoute>
              }
            />
            <Route
              path="/espace/admin"
              element={
                <ProtectedRoute allowedRoles={["admin"]}>
                  <DashboardAdmin />
                </ProtectedRoute>
              }
            />

            <Route path="*" element={<NotFound />} />
          </Routes>
        </Layout>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
