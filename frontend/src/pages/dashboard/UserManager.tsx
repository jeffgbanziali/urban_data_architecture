// src/pages/dashboard/UserManager.tsx
import React, { useEffect, useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { api, type Role, type UserOut } from "../../lib/api";

const roleOptions: Role[] = ["client", "employe", "admin"];

const UserManager: React.FC = () => {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<UserOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "employe" as Role });
  const [error, setError] = useState<string | null>(null);

  const loadUsers = () => {
    setLoading(true);
    api.get<UserOut[]>("/admin/users").then(setUsers).finally(() => setLoading(false));
  };

  useEffect(loadUsers, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post(`/admin/users?role=${form.role}`, {
        full_name: form.full_name,
        email: form.email,
        password: form.password,
      });
      setShowCreate(false);
      setForm({ full_name: "", email: "", password: "", role: "employe" });
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors de la création.");
    }
  };

  const changeRole = async (id: number, role: Role) => {
    await api.patch(`/admin/users/${id}/role`, { role });
    loadUsers();
  };

  const toggleActive = async (id: number, isActive: boolean) => {
    await api.patch(`/admin/users/${id}/active`, { is_active: !isActive });
    loadUsers();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-display text-ink font-semibold text-lg">Comptes utilisateurs ({users.length})</h2>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="px-4 py-2 rounded-full bg-ink text-cream text-sm font-semibold hover:bg-ink-light"
        >
          + Créer un compte employé / admin
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="bg-white border border-hairline rounded-xl p-5 mb-6 grid sm:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-sm text-ink/70">Nom complet</span>
            <input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className="mt-1 w-full rounded-lg border border-hairline px-3 py-2" />
          </label>
          <label className="block">
            <span className="text-sm text-ink/70">Email</span>
            <input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="mt-1 w-full rounded-lg border border-hairline px-3 py-2" />
          </label>
          <label className="block">
            <span className="text-sm text-ink/70">Mot de passe</span>
            <input type="password" required minLength={6} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="mt-1 w-full rounded-lg border border-hairline px-3 py-2" />
          </label>
          <label className="block">
            <span className="text-sm text-ink/70">Rôle</span>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })} className="mt-1 w-full rounded-lg border border-hairline px-3 py-2">
              <option value="employe">Employé</option>
              <option value="admin">Administrateur</option>
            </select>
          </label>
          {error && <p className="text-sm text-terracotta sm:col-span-2">{error}</p>}
          <div className="sm:col-span-2 flex gap-3">
            <button type="submit" className="px-5 py-2 rounded-full bg-terracotta text-white font-semibold">Créer le compte</button>
            <button type="button" onClick={() => setShowCreate(false)} className="px-5 py-2 rounded-full border border-hairline text-ink/70">Annuler</button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="text-ink/50">Chargement…</div>
      ) : (
        <div className="overflow-x-auto bg-white border border-hairline rounded-xl">
          <table className="w-full text-sm">
            <thead className="bg-cream-dark text-ink/70 text-left">
              <tr>
                <th className="px-4 py-3">Nom</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Rôle</th>
                <th className="px-4 py-3">Statut</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-hairline">
                  <td className="px-4 py-3 font-medium text-ink">{u.full_name}</td>
                  <td className="px-4 py-3 text-ink/70">{u.email}</td>
                  <td className="px-4 py-3">
                    <select
                      value={u.role}
                      disabled={u.id === currentUser?.id}
                      onChange={(e) => changeRole(u.id, e.target.value as Role)}
                      className="rounded border border-hairline px-2 py-1 bg-white disabled:opacity-50"
                    >
                      {roleOptions.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    <span className={u.is_active ? "text-verdigris" : "text-terracotta"}>
                      {u.is_active ? "Actif" : "Désactivé"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      disabled={u.id === currentUser?.id}
                      onClick={() => toggleActive(u.id, u.is_active)}
                      className="text-ink/70 hover:text-terracotta font-semibold disabled:opacity-40"
                    >
                      {u.is_active ? "Désactiver" : "Réactiver"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default UserManager;
