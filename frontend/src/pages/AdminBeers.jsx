import { useState } from "react";
import AdminBeerTable from "../components/AdminBeerTable";
import BeerEditModal from "../components/BeerEditModal";
import { useBeers } from "../hooks/useBeers";
import { createBeer, updateBeer } from "../api/beers";

export default function AdminBeers() {

    const { beers, fetchAdminBeers } = useBeers();

    const [selectedBeer, setSelectedBeer] = useState(null);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [isCreating, setIsCreating] = useState(false);
    const [search, setSearch] = useState("");

    // 🔥 NUEVO: obtener token
    const token = localStorage.getItem("token");

    const filteredBeers = beers.filter(beer =>
        beer.name.toLowerCase().includes(search.toLowerCase())
    );

    const handleEdit = (beer) => {
        setSelectedBeer({ ...beer });
        setIsCreating(false);
        setIsModalOpen(true);
    };

    const handleAddBeer = () => {
        setSelectedBeer(null);
        setIsCreating(true);
        setIsModalOpen(true);
    };

    const handleCloseModal = () => {
        setIsModalOpen(false);
        setSelectedBeer(null);
        setIsCreating(false);
    };

    const handleSave = async (data) => {
        try {

            const cleanData = {
                name: data.name || "",
                brewery: data.brewery || "Tiburón",
                style: data.style || "",
                color: data.color || "",
                abv: data.abv || 0,
                ibu: data.ibu || 0,
                description: data.description || "",
                origin: data.origin || "México",
                image_url: data.image_url || "",
                prices: data.prices || {},
                is_available: data.is_available ?? true
            };

            if (isCreating) {
                await createBeer(cleanData);
            } else {
                await updateBeer(selectedBeer.id, cleanData);
            }

            await fetchAdminBeers();
            handleCloseModal();

        } catch (error) {
            console.error(error);
            alert(JSON.stringify(error?.response?.data || error.message));
        }
    };

    return (
        <div>

            <h1>Admin Beers</h1>

            <input
                type="text"
                placeholder="Buscar cerveza..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                    marginBottom: "20px",
                    padding: "10px",
                    width: "100%",
                    maxWidth: "300px",
                    borderRadius: "8px",
                    border: "1px solid #333",
                    background: "#111",
                    color: "#fff"
                }}
            />

            <p style={{ opacity: 0.6 }}>
                {filteredBeers.length} resultados
            </p>

            <button onClick={handleAddBeer}>
                Add Beer
            </button>

            <AdminBeerTable
                beers={filteredBeers}
                token={token} // 🔥 FIX CLAVE
                onEdit={handleEdit}
                refresh={fetchAdminBeers}
            />

            <BeerEditModal
                isOpen={isModalOpen}
                onClose={handleCloseModal}
                onSave={handleSave}
                beer={selectedBeer}
                isCreating={isCreating}
            />

        </div>
    );
}