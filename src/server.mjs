import {createServer} from 'node:http'
import {readFileSync} from 'node:fs'
import {createClient} from 'hafas-client'
import {profile as insaProfile} from 'hafas-client/p/insa/index.js'
import {selectDeparture, selectUpcoming, describeDeparture, describeUpcoming} from './format.mjs'

const defaults = JSON.parse(readFileSync(new URL('../config.json', import.meta.url), 'utf8'))
const CACHE_MS = 45_000
const client = createClient(insaProfile, 'ha-havag-delay (personal Home Assistant use)')
/** @type {Map<string, {at: number, departures: object[]}>} */
const cache = new Map()

/**
 * @param {string} stop stop id
 * @param {number} minutes look-ahead window
 * @returns {Promise<object[]>} departures, cached for 45 s
 */
async function getDepartures(stop, minutes) {
    const key = `${stop}:${minutes}`
    const hit = cache.get(key)
    if (hit && Date.now() - hit.at < CACHE_MS) return hit.departures
    const res = await client.departures(stop, {when: new Date(), duration: minutes, results: 60})
    cache.set(key, {at: Date.now(), departures: res.departures})
    return res.departures
}

const server = createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost')
    if (url.pathname !== '/next' && url.pathname !== '/upcoming') {
        res.writeHead(404).end()
        return
    }
    const q = url.searchParams
    const opts = {
        stop: q.get('stop') || defaults.stop,
        line: q.get('line') || defaults.line,
        direction: q.get('direction') ?? defaults.direction,
        offsetMinutes: Number(q.get('offset') ?? defaults.offsetMinutes),
        toleranceMinutes: Number(q.get('tolerance') ?? defaults.toleranceMinutes),
    }
    try {
        const now = new Date()
        let body
        if (url.pathname === '/upcoming') {
            // next departure from now on (no offset), used for door-open notifications
            const departures = await getDepartures(opts.stop, 60)
            body = describeUpcoming(selectUpcoming(departures, {...opts, now}), opts.line, now)
        } else {
            const window = opts.offsetMinutes + opts.toleranceMinutes + 5
            const departures = await getDepartures(opts.stop, window)
            body = describeDeparture(selectDeparture(departures, {...opts, now}), opts.line)
        }
        res.writeHead(200, {'content-type': 'application/json; charset=utf-8'})
        res.end(JSON.stringify(body))
    } catch (error) {
        res.writeHead(502, {'content-type': 'application/json; charset=utf-8'})
        res.end(
            JSON.stringify({
                status: 'error',
                text: 'Fahrplanauskunft derzeit nicht erreichbar.',
                error: String(error.message || error),
            }),
        )
    }
})

const port = Number(process.env.PORT || 8099)
server.listen(port, () => console.log(`ha-havag-delay listening on :${port}`))
