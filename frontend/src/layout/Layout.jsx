import { useState } from "react";
import { readBackgroundPreference, writeBackgroundPreference } from "../backgrounds";
import "./Layout.css";

export default function Layout({ children }) {
    const [background, setBackground] = useState(readBackgroundPreference);

    function selectBackground(preset) {
        setBackground(writeBackgroundPreference(preset.id));
    }

    return (
        <div className="layout tap-list-layout" data-taplist-background={background.id} style={{ background: background.value, "--taplist-background": background.value }}>
            <header className="header tap-list-header" aria-hidden="true" />

            <main className="content">
                {typeof children === "function"
                    ? children({ background, onSelectBackground: selectBackground })
                    : children}
            </main>
        </div>
    )
}
