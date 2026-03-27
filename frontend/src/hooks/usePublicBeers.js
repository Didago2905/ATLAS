import { useState, useEffect } from "react";
import { fetchPublicBeers } from "../api/beers";

export function usePublicBeers() {

    const [beers, setBeers] = useState([]);

    const loadBeers = async () => {
        try {
            const data = await fetchPublicBeers();
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