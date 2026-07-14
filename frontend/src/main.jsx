import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import "./styles.css"

import CatalogSessionProvider from "./catalog/CatalogSessionProvider"

createRoot(document.getElementById('root')).render( <StrictMode> <CatalogSessionProvider> <App /> </CatalogSessionProvider> </StrictMode>,
)
