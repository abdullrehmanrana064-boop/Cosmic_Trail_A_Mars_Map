// ARIA — Astronaut Route Intelligence Assistant.
// Rule-based and offline (app/assistant.py): answers come from the terrain grid, the last
// route, bundled mineral sites and cited science cards — no language model.
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from 'react'
import { askAssistant, routeSummary, type AssistantAction, type AssistantReply } from '../api/cosmic'
import { useRouteStore } from '../store/routeStore'
import { getMapCenter } from './Globe'

interface Msg { role: 'aria' | 'user'; text: string; reply?: AssistantReply }

const GREETING =
  "Hello! I'm ARIA — your Astronaut Route Intelligence Assistant. I'm analysing terrain data for Gale Crater. " +
  'Ask me about slopes, hazards, elevation, minerals, your route or Mars geology. I answer from the NASA/USGS data ' +
  'loaded in COSMIC TRAIL and say where each answer comes from. I am rule-based (no AI model) and work offline.'

const QUICK = ['Am I safe here?', 'What minerals are nearby?', 'Analyze my route', 'How cold is it?']

/** Data-source badges shown under each reply. */
function badges(source: string): string[] {
  const s = source.toLowerCase(), out: string[] = []
  if (s.includes('hirise')) out.push('📡 HiRISE Data')
  if (s.includes('usgs')) out.push('🗺 USGS Gale DEM')
  if (s.includes('mola')) out.push('🛰 MOLA')
  if (s.includes('crism')) out.push('🔬 CRISM/OMEGA Data')
  if (s.includes('route')) out.push('🧭 Route result')
  if (s.includes('curiosity') || s.includes('science card') || s.includes('published')) out.push('📚 Published studies')
  return out.length ? out : ['ℹ No data source']
}

// Panel size: dragged from the top-left corner (the panel is anchored bottom-right).
const SIZE_KEY = 'cosmic-trail:aria-size'
const MIN = { w: 300, h: 200 }
const MAX = { w: 600, h: 500 }
const DEFAULT_SIZE = { w: 380, h: 420 }
const PANEL_BOTTOM = 344   // CSS .aria-panel bottom offset; the panel must also fit above it
type Size = { w: number; h: number }

const clampSize = (sz: Size): Size => ({
  w: Math.round(Math.min(MAX.w, Math.max(MIN.w, sz.w))),
  h: Math.round(Math.min(MAX.h, Math.max(MIN.h, sz.h))),
})

function loadSize(): Size {
  try {
    const v = JSON.parse(localStorage.getItem(SIZE_KEY) ?? 'null')
    if (v && Number.isFinite(v.w) && Number.isFinite(v.h)) return clampSize(v)
  } catch { /* storage unavailable: use the default */ }
  return DEFAULT_SIZE
}

function saveSize(sz: Size) {
  try { localStorage.setItem(SIZE_KEY, JSON.stringify(sz)) } catch { /* ignore */ }
}

/** Never let the panel run off the top or left of a small window. */
function useViewportLimit() {
  const get = () => ({ w: window.innerWidth - 32, h: window.innerHeight - PANEL_BOTTOM - 16 })
  const [lim, setLim] = useState(get)
  useEffect(() => {
    const on = () => setLim(get())
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return lim
}

const fmt = (lon: number, lat: number) =>
  `${Math.abs(lat).toFixed(3)}°${lat < 0 ? 'S' : 'N'}, ${Math.abs(lon).toFixed(3)}°${lon < 0 ? 'W' : 'E'}`

export default function Chatbot() {
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([{ role: 'aria', text: GREETING }])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const { dataset, response, activeMode, setEnd, setPickMessage } = useRouteStore()
  const setDestination = (a: AssistantAction) => {
    setEnd({ lon: a.lon, lat: a.lat })
    setPickMessage({ target: 'end', kind: 'ok', text: `B set to ${a.label} (${fmt(a.lon, a.lat)}) by ARIA. Press Find Route.` })
    setMsgs(m => [...m, { role: 'aria', text: `📍 Destination B set to ${a.label}. Press Find Route to plan the path.` }])
  }
  const [size, setSize] = useState<Size>(loadSize)
  const drag = useRef<{ x: number; y: number; w: number; h: number } | null>(null)
  const limit = useViewportLimit()

  // Auto-scroll to the latest message (also when the panel opens or is resized).
  // Jump (not smooth-scroll) to the newest message right after the DOM updates: a smooth scroll, or one
  // deferred to the next animation frame, can lag far behind while the 3D globe is busy rendering.
  useLayoutEffect(() => {
    const l = listRef.current
    if (l) l.scrollTop = l.scrollHeight
  }, [msgs, busy, open, size])
  useEffect(() => { if (open) inputRef.current?.focus() }, [open])

  const onResizeStart = (e: PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { x: e.clientX, y: e.clientY, w: size.w, h: size.h }
  }
  const onResizeMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    // Dragging up/left grows the panel (it is anchored at the bottom-right).
    setSize(clampSize({ w: d.w + (d.x - e.clientX), h: d.h + (d.y - e.clientY) }))
  }
  const onResizeEnd = useCallback(() => {
    if (!drag.current) return
    drag.current = null
    setSize(sz => { saveSize(sz); return sz })
  }, [])
  const onResizeKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 50 : 20
    const delta = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key]
    if (!delta) return
    e.preventDefault()
    setSize(sz => { const next = clampSize({ w: sz.w + delta[0], h: sz.h + delta[1] }); saveSize(next); return next })
  }
  const shown = { w: Math.min(size.w, Math.max(MIN.w, limit.w)), h: Math.min(size.h, Math.max(MIN.h, limit.h)) }

  const send = async (text: string) => {
    const q = text.trim()
    if (!q || busy) return
    setMsgs(m => [...m, { role: 'user', text: q }])
    setInput('')
    setBusy(true)
    const center = getMapCenter()
    const route = response?.routes[activeMode]
    try {
      const reply = await askAssistant(q, {
        current_lon: center?.lon, current_lat: center?.lat, dataset_id: dataset?.id,
        last_route: route ? routeSummary(route, response?.params_used.caution_slope_deg) : null,
      })
      setMsgs(m => [...m, { role: 'aria', text: reply.reply, reply }])
    } catch (e) {
      setMsgs(m => [...m, { role: 'aria', text: `I couldn't reach the COSMIC TRAIL backend (${(e as Error).message}).` }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button className={`aria-fab ${open ? 'open' : ''}`} data-occludes onClick={() => setOpen(o => !o)}
              aria-expanded={open} aria-controls="aria-panel" title="ARIA — rule-based terrain assistant">
        🤖 ARIA
      </button>
      {open && (
        <section id="aria-panel" className="aria-panel glass" data-occludes aria-label="ARIA assistant"
                 style={{ '--aria-w': `${shown.w}px`, '--aria-h': `${shown.h}px` } as CSSProperties}>
          <div className="aria-resize" role="separator" aria-orientation="horizontal" tabIndex={0}
               aria-label="Resize ARIA panel (drag, or use arrow keys)" title="Drag to resize"
               aria-valuemin={MIN.h} aria-valuemax={MAX.h} aria-valuenow={size.h}
               onPointerDown={onResizeStart} onPointerMove={onResizeMove}
               onPointerUp={onResizeEnd} onPointerCancel={onResizeEnd} onKeyDown={onResizeKey}>⤡</div>
          <header>
            <div>
              <h3>ARIA</h3>
              <p>Astronaut Route Intelligence Assistant · rule-based · offline</p>
            </div>
            <button className="close" aria-label="Close ARIA" onClick={() => setOpen(false)}>×</button>
          </header>
          <div className="aria-msgs" ref={listRef} aria-live="polite">
            {msgs.map((m, i) => (
              <div key={i} className={`aria-msg ${m.role}`}>
                <p>{m.text}</p>
                {(m.reply?.data as { action?: AssistantAction } | undefined)?.action?.type === 'set_destination' && (() => {
                  const a = (m.reply!.data as { action: AssistantAction }).action
                  return (
                    <button type="button" className="aria-action" onClick={() => setDestination(a)}>
                      📍 Set as Destination B — {a.label}
                    </button>
                  )
                })()}
                {m.reply && (
                  <div className="aria-meta">
                    {badges(m.reply.data_source).map(b => <span key={b} className="badge">{b}</span>)}
                    <span className={`conf ${m.reply.confidence}`}>confidence: {m.reply.confidence}</span>
                    <span className="where">📍 {fmt(m.reply.location.lon, m.reply.location.lat)}</span>
                    {m.reply.caveat && <small>{m.reply.caveat}</small>}
                  </div>
                )}
              </div>
            ))}
            {busy && <div className="aria-msg aria typing"><p>Analysing terrain…</p></div>}
          </div>
          <div className="aria-quick">
            {QUICK.map(q => <button key={q} onClick={() => send(q)} disabled={busy}>{q}</button>)}
          </div>
          <form className="aria-input" onSubmit={e => { e.preventDefault(); send(input) }}>
            <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)} maxLength={500}
                   placeholder="Ask about slope, hazards, minerals…" aria-label="Message ARIA" />
            <button type="submit" className="primary" disabled={busy || !input.trim()}>Send</button>
          </form>
          <p className="aria-foot">Answers use the point at the centre of the map. Not a safety certification.</p>
        </section>
      )}
    </>
  )
}
