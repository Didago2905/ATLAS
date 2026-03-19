import { useState, useEffect } from "react"

export default function BeerEditModal({ beer, onClose, onSave, isCreating, isOpen }) {

    const [form, setForm] = useState(null)
    const [pricesText, setPricesText] = useState("")

    useEffect(() => {

        // 🟢 MODO CREAR
        if (isCreating) {

            const defaultPrices = {
                taster: 0,
                pinta_chica: 0,
                pinta_grande: 0,
                jarra_chica: 0,
                jarra_grande: 0
            }

            setForm({
                name: "",
                style: "",
                abv: "",
                color: "",
                description: "",
                prices: defaultPrices
            })

            setPricesText(JSON.stringify(defaultPrices, null, 2))
            return
        }

        // 🟡 MODO EDITAR
        if (beer) {

            const safeBeer = { ...beer } // 🔥 evitar mutaciones

            setForm(safeBeer)

            if (safeBeer.prices) {
                setPricesText(JSON.stringify(safeBeer.prices, null, 2))
            } else {
                setPricesText("{}")
            }
        }

    }, [beer, isCreating])

    // 🔥 CONTROL REAL DEL MODAL
    if (!isOpen || !form) return null

    const handleChange = (e) => {
        const { name, value } = e.target

        let newValue = value

        if (name === "abv") {
            newValue = value === "" ? "" : parseFloat(value)
        }

        setForm({ ...form, [name]: newValue })
    }

    const handleSubmit = () => {

        let parsedPrices = {}

        try {
            parsedPrices = JSON.parse(pricesText)
        } catch (err) {
            alert("Prices JSON is invalid")
            return
        }

        const dataToSend = {
            ...form,
            prices: parsedPrices
        }

        console.log("DATA SENT:", dataToSend)

        onSave(dataToSend)
    }

    return (
        <div className="modal-overlay">
            <div className="modal">

                <h2>
                    {isCreating ? "Add Beer" : "Edit Beer"}
                </h2>

                <input
                    name="name"
                    value={form.name || ""}
                    onChange={handleChange}
                    placeholder="Name"
                />

                <input
                    name="style"
                    value={form.style || ""}
                    onChange={handleChange}
                    placeholder="Style"
                />

                <input
                    name="abv"
                    type="number"
                    step="0.1" // 🔥 PERMITE DECIMALES
                    value={form.abv}
                    onChange={(e) =>
                        setForm({
                            ...form,
                            abv: parseFloat(e.target.value)
                        })
                    }
                />

                <input
                    name="color"
                    value={form.color || ""}
                    onChange={handleChange}
                    placeholder="Color"
                />

                <textarea
                    name="description"
                    value={form.description || ""}
                    onChange={handleChange}
                    placeholder="Description"
                />

                <label>Prices (JSON)</label>

                <textarea
                    value={pricesText}
                    onChange={(e) => setPricesText(e.target.value)}
                    rows={6}
                />

                <div className="modal-buttons">
                    <button onClick={handleSubmit}>Save</button>
                    <button onClick={onClose}>Cancel</button>
                </div>

            </div>
        </div>
    )
}