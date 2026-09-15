import { useState } from "react";
import { resolveTapBackground } from "../backgrounds";
import TapListSettings from "./TapListSettings";
import "./Layout.css";

const STORAGE_KEY = "atlas_taplist_background";

export default function Layout({ children }) {
    const [background, setBackground] = useState(() => {
        try {
            return resolveTapBackground(localStorage.getItem(STORAGE_KEY));
        } catch {
            return resolveTapBackground(null);
        }
    });

    function selectBackground(preset) {
        setBackground(preset);
        try {
            localStorage.setItem(STORAGE_KEY, preset.id);
        } catch {
            // Keep the current session usable when storage is unavailable.
        }
    }

    return (
        <div className="layout tap-list-layout" data-taplist-background={background.id} style={{ background: background.value, "--taplist-background": background.value }}>
            <header className="header tap-list-header">
                <h1 className="tap-list-branding">
                    <span className="tap-list-branding__name">TIBURÓN</span>
                </h1>
                <TapListSettings background={background} onSelect={selectBackground} />
            </header>

            <main className="content">
                {children}
            </main>
        </div>
    )
}
