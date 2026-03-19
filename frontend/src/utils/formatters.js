export const formatABV = (abv) => {
    if (abv === null || abv === undefined) return "-";

    const value = Number(abv);
    if (isNaN(value)) return "-";

    return `${value.toFixed(1)}%`;
};