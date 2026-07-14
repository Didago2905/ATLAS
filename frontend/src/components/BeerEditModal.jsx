import { useState, useEffect } from "react"
import { uploadBeerCardBackground } from "../api/beers"

const sectionTitleStyle = {
    marginTop: "18px",
    marginBottom: "8px",
    fontSize: "14px",
    fontWeight: 600,
    color: "#ddd",
}

const assetBoxStyle = {
    marginTop: "8px",
    padding: "12px",
    borderRadius: "8px",
    border: "1px solid #333",
    background: "#161616",
}

const assetPreviewStyle = {
    width: "72px",
    height: "128px",
    objectFit: "cover",
    borderRadius: "6px",
    display: "block",
    marginBottom: "8px",
}

const assetPlaceholderStyle = {
    width: "72px",
    height: "128px",
    borderRadius: "6px",
    border: "1px dashed #444",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "11px",
    color: "#888",
    textAlign: "center",
    padding: "8px",
    marginBottom: "8px",
    boxSizing: "border-box",
}

const uploadLabelStyle = {
    display: "inline-block",
    padding: "6px 10px",
    background: "#333",
    color: "#fff",
    borderRadius: "6px",
    fontSize: "12px",
    cursor: "pointer",
}

const assetUrlStyle = {
    marginTop: "6px",
    fontSize: "11px",
    color: "#777",
    wordBreak: "break-all",
}

export default function BeerEditModal({
    beer,
    onClose,
    onSave,
    isCreating,
    isOpen,
    onAssetsUpdated,
}) {

    const [form, setForm] = useState(null)
    const [pricesText, setPricesText] = useState("")
    const [uploadingTap, setUploadingTap] = useState(false)
    const [uploadingCardBackground, setUploadingCardBackground] = useState(false)

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

    if (!isOpen || !form) return null

    const beerId = beer?.id
    const canUploadAssets = !isCreating && beerId

    const handleChange = (e) => {
        const { name, value } = e.target

        let newValue = value

        if (name === "abv") {
            newValue = value === "" ? "" : parseFloat(value)
        }

        setForm({ ...form, [name]: newValue })
    }

    const handleTapImageUpload = async (e) => {
        const file = e.target.files[0]
        if (!file || !beerId) return

        const previewUrl = URL.createObjectURL(file)
        setForm((prev) => ({ ...prev, image_url: previewUrl }))
        setUploadingTap(true)

        const formData = new FormData()
        formData.append("file", file)

        try {
            const res = await fetch(`/api/admin/beers/${beerId}/upload-image`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${localStorage.getItem("token")}`,
                },
                body: formData,
            })

            if (res.status === 401) {
                localStorage.removeItem("token")
                window.location.href = "/login"
                return
            }

            if (!res.ok) throw new Error("Tap image upload failed")

            const data = await res.json()
            setForm((prev) => ({ ...prev, image_url: data.image_url }))
            await onAssetsUpdated?.()
        } catch (err) {
            console.error(err)
            alert("Error uploading tap image")
        } finally {
            setUploadingTap(false)
            e.target.value = ""
        }
    }

    const handleCardBackgroundUpload = async (e) => {
        const file = e.target.files[0]
        if (!file || !beerId) return

        const previewUrl = URL.createObjectURL(file)
        setForm((prev) => ({ ...prev, beercard_background_url: previewUrl }))
        setUploadingCardBackground(true)

        try {
            const data = await uploadBeerCardBackground(beerId, file)
            setForm((prev) => ({
                ...prev,
                beercard_background_url: data.beercard_background_url,
            }))
            await onAssetsUpdated?.()
        } catch (err) {
            console.error(err)
            alert("Error uploading BeerCard background")
        } finally {
            setUploadingCardBackground(false)
            e.target.value = ""
        }
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

                <p style={sectionTitleStyle}>Beer Information</p>

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
                    step="0.1"
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

                <p style={sectionTitleStyle}>Prices</p>

                <textarea
                    value={pricesText}
                    onChange={(e) => setPricesText(e.target.value)}
                    rows={6}
                />

                {canUploadAssets ? (
                    <>
                        <p style={sectionTitleStyle}>Tap Image</p>

                        <div style={assetBoxStyle}>
                            {form.image_url ? (
                                <img
                                    src={form.image_url}
                                    alt="Tap"
                                    style={assetPreviewStyle}
                                />
                            ) : (
                                <div style={assetPlaceholderStyle}>
                                    No tap image uploaded
                                </div>
                            )}

                            <input
                                type="file"
                                accept="image/*"
                                onChange={handleTapImageUpload}
                                style={{ display: "none" }}
                                id="beer-edit-tap-image"
                                disabled={uploadingTap}
                            />

                            <label
                                htmlFor="beer-edit-tap-image"
                                style={{
                                    ...uploadLabelStyle,
                                    opacity: uploadingTap ? 0.6 : 1,
                                    pointerEvents: uploadingTap ? "none" : "auto",
                                }}
                            >
                                {uploadingTap
                                    ? "Uploading..."
                                    : form.image_url
                                        ? "Replace tap image"
                                        : "Upload tap image"}
                            </label>

                            {form.image_url && (
                                <div style={assetUrlStyle}>{form.image_url}</div>
                            )}
                        </div>

                        <p style={sectionTitleStyle}>BeerCard Background</p>

                        <div style={assetBoxStyle}>
                            {form.beercard_background_url ? (
                                <img
                                    src={form.beercard_background_url}
                                    alt="BeerCard background"
                                    style={assetPreviewStyle}
                                />
                            ) : (
                                <div style={assetPlaceholderStyle}>
                                    No BeerCard background uploaded
                                </div>
                            )}

                            <input
                                type="file"
                                accept="image/*"
                                onChange={handleCardBackgroundUpload}
                                style={{ display: "none" }}
                                id="beer-edit-card-background"
                                disabled={uploadingCardBackground}
                            />

                            <label
                                htmlFor="beer-edit-card-background"
                                style={{
                                    ...uploadLabelStyle,
                                    opacity: uploadingCardBackground ? 0.6 : 1,
                                    pointerEvents: uploadingCardBackground
                                        ? "none"
                                        : "auto",
                                }}
                            >
                                {uploadingCardBackground
                                    ? "Uploading..."
                                    : form.beercard_background_url
                                        ? "Replace BeerCard background"
                                        : "Upload BeerCard background"}
                            </label>

                            {form.beercard_background_url && (
                                <div style={assetUrlStyle}>
                                    {form.beercard_background_url}
                                </div>
                            )}
                        </div>
                    </>
                ) : (
                    <p
                        style={{
                            marginTop: "16px",
                            fontSize: "12px",
                            color: "#888",
                        }}
                    >
                        Save the beer first to upload tap and BeerCard background
                        images.
                    </p>
                )}

                <div className="modal-buttons">
                    <button onClick={handleSubmit}>Save</button>
                    <button onClick={onClose}>Cancel</button>
                </div>

            </div>
        </div>
    )
}
