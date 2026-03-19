export default function Layout({ children }) {
    return (
        <div className="layout">
            <header className="header">
                <h1>ATLAS</h1>
                <p>Taproom Manager</p>
            </header>

            <main className="content">
                {children}
            </main>
        </div>
    )
}