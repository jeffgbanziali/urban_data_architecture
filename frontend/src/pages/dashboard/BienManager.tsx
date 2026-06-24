// src/pages/dashboard/BienManager.tsx
import React, { useEffect, useState } from "react";
import { api, type Bien } from "../../lib/api";

const TYPES = ["Studio", "T2", "T3", "T4", "T5+", "Maison"];
const STATUTS: Bien["statut"][] = ["disponible", "sous_offre", "vendu"];

const emptyForm = {
  titre: "",
  description: "",
  arrondissement: 1,
  type_bien: "T2",
  prix: 0,
  surface_m2: 0,
  photo_url: "",
  statut: "disponible" as Bien["statut"],
};

const BienManager: React.FC<{ canDelete: boolean }> = ({ canDelete }) => {
  const [biens, setBiens] = useState<Bien[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const loadBiens = () => {
    setLoading(true);
    api.get<Bien[]>("/biens").then(setBiens).finally(() => setLoading(false));
  };

  useEffect(loadBiens, []);

  const startCreate = () => {
    setEditingId(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const startEdit = (bien: Bien) => {
    setEditingId(bien.id);
    setForm({
      titre: bien.titre,
      description: bien.description || "",
      arrondissement: bien.arrondissement,
      type_bien: bien.type_bien,
      prix: bien.prix,
      surface_m2: bien.surface_m2,
      photo_url: bien.photo_url || "",
      statut: bien.statut,
    });
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      if (editingId) {
        await api.put(`/biens/${editingId}`, form);
      } else {
        await api.post("/biens", form);
      }
      setShowForm(false);
      loadBiens();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors de l'enregistrement.");
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Supprimer définitivement ce bien ?")) return;
    await api.delete(`/biens/${id}`);
    loadBiens();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-display text-ink font-semibold text-lg">Portefeuille de biens ({biens.length})</h2>
        <button
          onClick={startCreate}
          className="px-4 py-2 rounded-full bg-terracotta text-white text-sm font-semibold hover:bg-terracotta-light"
        >
          + Ajouter un bien
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white border border-hairline rounded-xl p-5 mb-6 grid sm:grid-cols-2 gap-4">
          <label className="block sm:col-span-2">
            <span className="text-sm text-ink/70">Titre</span>
            <input
              required
              value={form.titre}
              onChange={(e) => setForm({ ...form, titre: e.target.value })}
              className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
            />
          </label>
          <label className="block sm:col-span-2">
            <span className="text-sm text-ink/70">Description</span>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
              rows={2}
            />
          </label>
          <label className="block">
            <span className="text-sm text-ink/70">Arrondissement</span>
            <select
              value={form.arrondissement}
              onChange={(e) => setForm({ ...form, arrondissement: Number(e.target.value) })}
              className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
            >
              {Array.from({ length: 20 }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>{n}e</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm text-ink/70">Typologie</span>
            <select
              value={form.type_bien}
              onChange={(e) => setForm({ ...form, type_bien: e.target.value })}
              className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm text-ink/70">Prix (€)</span>
            <input
              type="number"
              min={0}
              required
              value={form.prix}
              onChange={(e) => setForm({ ...form, prix: Number(e.target.value) })}
              className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
            />
          </label>
          <label className="block">
            <span className="text-sm text-ink/70">Surface (m²)</span>
            <input
              type="number"
              min={0}
              required
              value={form.surface_m2}
              onChange={(e) => setForm({ ...form, surface_m2: Number(e.target.value) })}
              className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
            />
          </label>
          <label className="block">
            <span className="text-sm text-ink/70">Statut</span>
            <select
              value={form.statut}
              onChange={(e) => setForm({ ...form, statut: e.target.value as Bien["statut"] })}
              className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
            >
              {STATUTS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm text-ink/70">URL photo (optionnel)</span>
            <input
              value={form.photo_url}
              onChange={(e) => setForm({ ...form, photo_url: e.target.value })}
              className="mt-1 w-full rounded-lg border border-hairline px-3 py-2"
              placeholder="https://…"
            />
          </label>

          {error && <p className="text-sm text-terracotta sm:col-span-2">{error}</p>}

          <div className="sm:col-span-2 flex gap-3">
            <button type="submit" className="px-5 py-2 rounded-full bg-ink text-cream font-semibold">
              {editingId ? "Enregistrer les modifications" : "Créer le bien"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="px-5 py-2 rounded-full border border-hairline text-ink/70">
              Annuler
            </button>
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
                <th className="px-4 py-3">Titre</th>
                <th className="px-4 py-3">Arr.</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Prix</th>
                <th className="px-4 py-3">Statut</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {biens.map((b) => (
                <tr key={b.id} className="border-t border-hairline">
                  <td className="px-4 py-3 font-medium text-ink">{b.titre}</td>
                  <td className="px-4 py-3">{b.arrondissement}e</td>
                  <td className="px-4 py-3">{b.type_bien}</td>
                  <td className="px-4 py-3 font-mono-data">{b.prix.toLocaleString("fr-FR")} €</td>
                  <td className="px-4 py-3">{b.statut}</td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <button onClick={() => startEdit(b)} className="text-ink/70 hover:text-terracotta font-semibold">
                      Modifier
                    </button>
                    {canDelete && (
                      <button onClick={() => handleDelete(b.id)} className="text-terracotta hover:text-terracotta-light font-semibold">
                        Supprimer
                      </button>
                    )}
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

export default BienManager;
