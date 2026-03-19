import BeerCard from "./BeerCard"

export default function BeerList({ beers }) {
  return (
    <div className="beer-grid">
      {beers.map((beer) => (
        <BeerCard key={beer.id} beer={beer} />
      ))}
    </div>
  )
}