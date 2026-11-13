import {createClient} from 'hafas-client'
import {profile as insaProfile} from 'hafas-client/p/insa/index.js'

const query = process.argv.slice(2).join(' ')
if (!query) {
    console.error('Usage: npm run find-stop -- "<stop name>"')
    process.exit(1)
}

const client = createClient(insaProfile, 'ha-havag-delay (personal Home Assistant use)')
const stops = await client.locations(query, {results: 8, addresses: false, poi: false})
for (const s of stops) {
    console.log(`${s.id}\t${s.name}`)
}
