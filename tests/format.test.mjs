import {test} from 'node:test'
import assert from 'node:assert/strict'
import {selectDeparture, selectUpcoming, describeDeparture, describeUpcoming} from '../src/format.mjs'

const dep = (planned, delay, extra = {}) => ({
    line: {name: 'Str 10'},
    direction: 'Halle (Saale), Soltauer Str.',
    plannedWhen: planned,
    when: delay == null ? null : new Date(new Date(planned).getTime() + delay * 1000).toISOString(),
    delay,
    ...extra,
})
const now = new Date('2026-11-13T09:30:00+01:00')
const opts = {line: '10', direction: 'Soltauer Str.', now, offsetMinutes: 8, toleranceMinutes: 3}

test('selects the departure planned 8 minutes ahead', () => {
    const list = [
        dep('2026-11-13T09:23:00+01:00', 0),
        dep('2026-11-13T09:38:00+01:00', 180),
        dep('2026-11-13T09:53:00+01:00', 0),
    ]
    assert.equal(selectDeparture(list, opts).plannedWhen, '2026-11-13T09:38:00+01:00')
})

test('ignores other lines and other directions', () => {
    const list = [
        {...dep('2026-11-13T09:38:00+01:00', 0), line: {name: 'Str 1'}},
        {...dep('2026-11-13T09:38:00+01:00', 0), direction: 'Halle (Saale), Hauptbahnhof (Tram/Bus)'},
        {...dep('2026-11-13T09:38:00+01:00', 0), line: {name: 'Bus 110'}},
    ]
    assert.equal(selectDeparture(list, opts), null)
})

test('returns null outside the tolerance', () => {
    assert.equal(selectDeparture([dep('2026-11-13T09:53:00+01:00', 0)], opts), null)
    assert.equal(selectDeparture([], opts), null)
})

test('on time', () => {
    const r = describeDeparture(dep('2026-11-13T09:38:00+01:00', 0), '10')
    assert.equal(r.status, 'on-time')
    assert.match(r.text, /pünktlich/)
})

test('early counts as on time', () => {
    assert.equal(describeDeparture(dep('2026-11-13T09:38:00+01:00', -60), '10').status, 'on-time')
})

test('delayed', () => {
    const r = describeDeparture(dep('2026-11-13T09:38:00+01:00', 180), '10')
    assert.equal(r.status, 'delayed')
    assert.equal(r.delayMinutes, 3)
    assert.match(r.text, /09:38.*09:41.*3 Minuten verspätet/)
})

test('singular minute', () => {
    assert.match(describeDeparture(dep('2026-11-13T09:38:00+01:00', 60), '10').text, /1 Minute verspätet/)
})

test('cancelled', () => {
    const r = describeDeparture(dep('2026-11-13T09:38:00+01:00', null, {cancelled: true}), '10')
    assert.equal(r.status, 'cancelled')
    assert.match(r.text, /fällt aus/)
})

test('no realtime data falls back to planned time', () => {
    const r = describeDeparture(dep('2026-11-13T09:38:00+01:00', null), '10')
    assert.equal(r.status, 'no-realtime')
    assert.match(r.text, /09:38/)
})

test('not found', () => {
    assert.equal(describeDeparture(null, '10').status, 'not-found')
})

const upOpts = {line: '10', direction: 'Soltauer Str.', now}

test('selectUpcoming takes the next departure from now, using the predicted time', () => {
    const list = [
        dep('2026-11-13T09:23:00+01:00', 0),
        dep('2026-11-13T09:28:00+01:00', 240), // late, predicted 09:32, still ahead
        dep('2026-11-13T09:38:00+01:00', 0),
    ]
    assert.equal(selectUpcoming(list, upOpts).plannedWhen, '2026-11-13T09:28:00+01:00')
})

test('selectUpcoming skips cancelled, other lines and other directions', () => {
    const list = [
        dep('2026-11-13T09:31:00+01:00', null, {cancelled: true}),
        {...dep('2026-11-13T09:32:00+01:00', 0), line: {name: 'Bus 21'}},
        {...dep('2026-11-13T09:33:00+01:00', 0), direction: 'Halle (Saale), Hauptbahnhof (Tram/Bus)'},
        dep('2026-11-13T09:38:00+01:00', 0),
    ]
    assert.equal(selectUpcoming(list, upOpts).plannedWhen, '2026-11-13T09:38:00+01:00')
    assert.equal(selectUpcoming([], upOpts), null)
})

test('describeUpcoming adds the minutes until departure', () => {
    const r = describeUpcoming(dep('2026-11-13T09:38:00+01:00', 180), '10', now)
    assert.equal(r.inMinutes, 11) // predicted 09:41, now 09:30
    assert.match(r.text, /3 Minuten verspätet\)\. Abfahrt in 11 Min\.$/)
})

test('describeUpcoming without a departure', () => {
    const r = describeUpcoming(null, '10', now)
    assert.equal(r.status, 'not-found')
    assert.equal(r.inMinutes, null)
})
