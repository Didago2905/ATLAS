export async function audit(event, beerId = null, metadata = null) {

    console.log("AUDIT START");

    try {

        const response = await fetch("/api/audit/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },

            body: JSON.stringify({
                event,
                beer_id: beerId,
                metadata,
            }),
        });

        console.log("AUDIT STATUS:", response.status);

    } catch (err) {

        console.error("AUDIT ERROR:", err);
    }
}