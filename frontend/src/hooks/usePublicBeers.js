import { useState, useEffect } from "react";
import { fetchBeers } from "../api/beers";

export function usePublicBeers() {

    const [beers, setBeers] = useState([]);

    const loadBeers = async () => {
        try {
            const data = await fetchBeers(); // 🔥 endpoint público
            setBeers(data);
        } catch (error) {
            console.error("ERROR FETCHING PUBLIC BEERS:", error);
        }
    };

    useEffect(() => {
        loadBeers();
    }, []);

    return {
        beers,
        refresh: loadBeers
    };
}