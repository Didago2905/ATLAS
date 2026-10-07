import { useEffect, useState } from "react";

export default function useTutorialImage(src, enabled) {
    const [preparedSrc, setPreparedSrc] = useState(null);

    useEffect(() => {
        if (!enabled) return;
        let cancelled = false;
        const image = new Image();
        const finish = () => {
            if (!cancelled) setPreparedSrc(src);
        };
        image.onerror = finish;
        image.onload = async () => {
            try {
                if (image.decode) await image.decode();
            } catch {
                // Fall back to normal rendering if preparation fails.
            }
            finish();
        };
        image.src = src;
        return () => {
            cancelled = true;
            image.onload = null;
            image.onerror = null;
        };
    }, [src, enabled]);

    return preparedSrc === src;
}
