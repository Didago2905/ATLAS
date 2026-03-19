import Layout from "../layout/Layout"
import BeerList from "../components/BeerList"
import { usePublicBeers } from "../hooks/usePublicBeers";

export default function Home() {

    const { beers } = usePublicBeers()

    return (
        <Layout>
            <BeerList beers={beers} />
        </Layout>
    )
}