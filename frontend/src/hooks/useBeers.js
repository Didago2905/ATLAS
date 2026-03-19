import { useState, useEffect } from "react";
import { fetchAdminBeers } from "../api/beers";

export function useBeers() {

    const [beers, setBeers] = useState([]);

    const loadBeers = async () => {
        try {
            const data = await fetchAdminBeers();
            setBeers(data);
        } catch (error) {
            console.error("ERROR FETCHING BEERS:", error);
        }
    };

    useEffect(() => {
        loadBeers();
    }, []);

    return {
        beers,
        fetchAdminBeers: loadBeers // 🔥 CLAVE
    };
}