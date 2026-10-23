const BASE = '/api'

async function request(path, opts = {}) {
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    let msg = res.statusText
    try { const j = await res.json(); msg = j.detail || JSON.stringify(j) } catch { /* ignore */ }
    throw new Error(msg)
  }
  return res.json()
}

export const get = (path) => request(path)
export const post = (path, body) =>
  request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) })

/**
 * POST a body and consume a server-sent-event stream, calling `onEvent` for each event.
 * Resolves when the server closes the stream. Pass `signal` to abort.
 */
export async function stream(path, body, onEvent, signal) {
  const res = await fetch(BASE + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}), signal,
  })
  if (!res.ok) {
    let msg = res.statusText
    try { const j = await res.json(); msg = j.detail || JSON.stringify(j) } catch { /* ignore */ }
    throw new Error(msg)
  }
  if (!res.body) throw new Error('streaming is not supported by this browser')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''          // keep the partial event for the next chunk
    for (const block of blocks) {
      for (const line of block.split('\n')) {
        if (!line.startsWith('data: ')) continue
        try { onEvent(JSON.parse(line.slice(6))) } catch { /* ignore a malformed frame */ }
      }
    }
  }
}
