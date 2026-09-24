import BeerCard from "./BeerCard";
import PeekOverlay from "./PeekOverlay";

export default function BeerPeek({ beer, onClose }) {
    return (
        <PeekOverlay
            data-atlas-beer-peek
            label={beer.name}
            onClose={onClose}
            panelStyle={{
                width: "100%",
                maxWidth: "340px",
                maxHeight: "calc(100dvh - 40px)",
                overflowY: "auto",
                overscrollBehavior: "contain",
                borderRadius: "16px",
                boxShadow: "0 12px 40px rgba(0,0,0,0.45)",
            }}
        >
            <BeerCard key={beer.id} beer={beer} />
        </PeekOverlay>
    );
}
