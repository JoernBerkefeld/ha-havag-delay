const TZ = 'Europe/Berlin'

/**
 * @param {string} iso ISO timestamp
 * @returns {string} HH:MM in Halle local time
 */
export function formatTime(iso) {
    return new Date(iso).toLocaleTimeString('de-DE', {
        hour: '2-digit',
        minute: '2-digit',
        timeZone: TZ,
    })
}

/**
 * @param {string | undefined} name e.g. "Str 10"
 * @param {string} line e.g. "10"
 * @returns {boolean} true if the last token of the line name equals the line number
 */
function lineMatches(name, line) {
    return (name || '').trim().split(/\s+/).pop() === String(line)
}

/**
 * Picks the departure of the given line/direction whose planned time is closest
 * to now + offset, within the tolerance.
 *
 * @param {object[]} departures hafas-client departures
 * @param {{line: string, direction?: string, now: Date, offsetMinutes: number, toleranceMinutes: number}} opts selection options
 * @returns {object | null} the matching departure or null
 */
export function selectDeparture(departures, {line, direction, now, offsetMinutes, toleranceMinutes}) {
    const target = now.getTime() + offsetMinutes * 60_000
    const tolerance = toleranceMinutes * 60_000
    let best = null
    let bestDiff = Number.POSITIVE_INFINITY
    for (const dep of departures) {
        if (!lineMatches(dep.line?.name, line)) continue
        if (direction && !(dep.direction || '').toLowerCase().includes(direction.toLowerCase())) continue
        const planned = dep.plannedWhen || dep.when
        if (!planned) continue
        const diff = Math.abs(new Date(planned).getTime() - target)
        if (diff <= tolerance && diff < bestDiff) {
            best = dep
            bestDiff = diff
        }
    }
    return best
}

/**
 * Picks the next non-cancelled departure of the line/direction that has not left yet
 * (by predicted time, falling back to the planned time).
 *
 * @param {object[]} departures hafas-client departures
 * @param {{line: string, direction?: string, now: Date}} opts selection options
 * @returns {object | null} the next departure or null
 */
export function selectUpcoming(departures, {line, direction, now}) {
    let best = null
    let bestTime = Number.POSITIVE_INFINITY
    for (const dep of departures) {
        if (dep.cancelled) continue
        if (!lineMatches(dep.line?.name, line)) continue
        if (direction && !(dep.direction || '').toLowerCase().includes(direction.toLowerCase())) continue
        const when = dep.when || dep.plannedWhen
        if (!when) continue
        const t = new Date(when).getTime()
        if (t >= now.getTime() && t < bestTime) {
            best = dep
            bestTime = t
        }
    }
    return best
}

/**
 * Like describeDeparture, plus the minutes until departure.
 *
 * @param {object | null} dep selected departure or null
 * @param {string} line line number for the text
 * @param {Date} now current time
 * @returns {object} result for Home Assistant, with inMinutes
 */
export function describeUpcoming(dep, line, now) {
    const result = describeDeparture(dep, line)
    if (!dep) return {...result, inMinutes: null}
    const when = new Date(dep.when || dep.plannedWhen).getTime()
    const inMinutes = Math.max(0, Math.round((when - now.getTime()) / 60_000))
    return {...result, inMinutes, text: `${result.text} Abfahrt in ${inMinutes} Min.`}
}

/**
 * @param {object | null} dep selected departure or null
 * @param {string} line line number for the text
 * @returns {{status: string, planned: string|null, actual: string|null, delayMinutes: number|null, cancelled: boolean, text: string}} result for Home Assistant
 */
export function describeDeparture(dep, line) {
    if (!dep) {
        return {
            status: 'not-found',
            planned: null,
            actual: null,
            delayMinutes: null,
            cancelled: false,
            text: `Keine passende Abfahrt der Linie ${line} gefunden.`,
        }
    }
    const planned = dep.plannedWhen || dep.when
    const plannedTime = formatTime(planned)
    if (dep.cancelled) {
        return {
            status: 'cancelled',
            planned,
            actual: null,
            delayMinutes: null,
            cancelled: true,
            text: `Linie ${line} um ${plannedTime} fällt aus.`,
        }
    }
    if (dep.when == null || dep.delay == null) {
        return {
            status: 'no-realtime',
            planned,
            actual: null,
            delayMinutes: null,
            cancelled: false,
            text: `Linie ${line} um ${plannedTime} geplant, keine Echtzeitdaten verfügbar.`,
        }
    }
    const delayMinutes = Math.round(dep.delay / 60)
    const actualTime = formatTime(dep.when)
    if (delayMinutes <= 0) {
        return {
            status: 'on-time',
            planned,
            actual: dep.when,
            delayMinutes: 0,
            cancelled: false,
            text: `Linie ${line} um ${plannedTime} ist pünktlich.`,
        }
    }
    const unit = delayMinutes === 1 ? 'Minute' : 'Minuten'
    return {
        status: 'delayed',
        planned,
        actual: dep.when,
        delayMinutes,
        cancelled: false,
        text: `Linie ${line} um ${plannedTime} geplant, tatsächlich ${actualTime} (${delayMinutes} ${unit} verspätet).`,
    }
}
