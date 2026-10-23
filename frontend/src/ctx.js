import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { get } from './api'

export const AppCtx = createContext(null)
export const useApp = () => useContext(AppCtx)

/** Fetch JSON; refetches when `tick` (global refresh counter) changes or every `interval` ms. */
export function useFetch(path, interval = 0) {
  const { tick } = useApp()
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const alive = useRef(true)
  const load = useCallback(async () => {
    try {
      const data = await get(path)
      if (alive.current) setState({ data, error: null, loading: false })
    } catch (e) {
      if (alive.current) setState((s) => ({ ...s, error: e.message, loading: false }))
    }
  }, [path])
  useEffect(() => {
    alive.current = true
    load()
    const id = interval ? setInterval(load, interval) : null
    return () => { alive.current = false; if (id) clearInterval(id) }
  }, [load, tick, interval])
  return { ...state, reload: load }
}
