import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

export const CatalogSessionContext = createContext({
  beers: [],
  isLoading: false,
  error: null,
  refresh: () => { },
});

export default function CatalogSessionProvider({
  children,
}) {
  const [beers, setBeers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const isFetchingRef = useRef(false);

  const fetchCatalog = useCallback(async () => {
    if (isFetchingRef.current) {
      console.log(
        "CATALOG FETCH SKIPPED (IN FLIGHT)"
      );
      return;
    }

    isFetchingRef.current = true;

    try {
      console.log("CATALOG FETCH START");

      const res = await fetch("/api/public/tap");

      if (!res.ok) {
        throw new Error(
          `HTTP ${res.status}`
        );
      }

      const data = await res.json();

      // ⭐ FEATURED TRACKING (migrado desde useTapBeers)

      const featuredBeers = data.filter(
        beer => beer.is_featured
      );

      const latestFeaturedUpdate = Math.max(
        ...featuredBeers.map(
          beer => beer.featured_updated_at || 0
        ),
        0
      );

      const lastSeen = Number(
        localStorage.getItem(
          "last_seen_featured_update"
        ) || 0
      );

      if (latestFeaturedUpdate > lastSeen) {

        console.log(
          "⭐ NEW FEATURED EVENT"
        );

        localStorage.setItem(
          "last_seen_featured_update",
          latestFeaturedUpdate
        );
      }

      console.log(
        "CATALOG FETCH SUCCESS",
        data.length
      );

      setBeers(prev => {
        const same =
          JSON.stringify(prev) ===
          JSON.stringify(data);

        if (same) {
          console.log(
            "CATALOG STABLE (NO UPDATE)"
          );

          return prev;
        }

        console.log(
          "CATALOG CHANGED (UPDATE)"
        );

        return data;
      });

    } catch (err) {
      console.error(
        "CATALOG FETCH ERROR",
        err
      );

      setError(err);
    } finally {
      isFetchingRef.current = false;
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  useEffect(() => {

    document.body.dataset.atlasLoading =
      isLoading ? "true" : "false";

  }, [isLoading]);

  const refresh = useCallback(() => {
    console.log(
      "REFRESH REQUESTED"
    );

    fetchCatalog();
  }, [fetchCatalog]);

  const value = useMemo(
    () => ({
      beers,
      isLoading,
      error,
      refresh,
    }),
    [beers, isLoading, error, refresh]
  );

  useEffect(() => {

    document.body.dataset.atlasLoading =
      String(isLoading);

  }, [isLoading]);

  useEffect(() => {

    document.body.dataset.atlasReady = "false";

    if (!isLoading && beers.length > 0) {

      requestAnimationFrame(() => {

        document.body.dataset.atlasReady =
          "true";

      });

    }

  }, [isLoading, beers]);

  console.log(
    "PROVIDER RENDER",
    beers.length
  );

  return (
    <CatalogSessionContext.Provider value={value}>
      {children}
    </CatalogSessionContext.Provider>
  );
}