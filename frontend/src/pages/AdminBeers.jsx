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

    const handleEdit = (beer) => {
        setSelectedBeer({ ...beer }); // 🔥 clon
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

            // 🔥 LIMPIAMOS EL PAYLOAD
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
                console.log("CREATING BEER...");
                await createBeer(cleanData);
            } else {
                console.log("UPDATING BEER...");
                await updateBeer(selectedBeer.id, cleanData);
            }

            await fetchAdminBeers();
            handleCloseModal();

        } catch (error) {
            console.error("ERROR COMPLETO:", error);
            console.error("RESPONSE:", error?.response?.data);
            alert(JSON.stringify(error?.response?.data || error.message));
        }
    };


    return (
        <div>

            {/* 🔥 HEADER ADMIN */}
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem" }}>

                <h1>Admin Beers</h1>


            </div>

            {/* 🔥 ACCIONES */}
            <button onClick={handleAddBeer}>
                Add Beer
            </button>

            <AdminBeerTable
                beers={beers}
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