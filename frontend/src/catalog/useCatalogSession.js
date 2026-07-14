import { useContext } from "react";
import { CatalogSessionContext } from "./CatalogSessionProvider";

export default function useCatalogSession() {
  return useContext(CatalogSessionContext);
}