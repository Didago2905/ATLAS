import { useEffect, useState } from "react";

export default function useTapBeers() {
    const [beers, setBeers] = useState([]);

    const fetchTap = async () => {
        try {
            const res = await fetch("/api/public/tap");

            if (!res.ok) {
                console.error("HTTP ERROR:", res.status);
                return;
            }

            const data = await res.json();

            console.log("TAP DATA:", data); // debug ligero

            if (Array.isArray(data)) {
                setBeers(prev => {
                    const same = JSON.stringify(prev) === JSON.stringify(data);
                    return same ? prev : data;
                });
            }

        } catch (error) {
            console.error("FETCH TAP ERROR:", error);
        }
    };

    useEffect(() => {
        fetchTap();
    }, []);

    return beers;
}