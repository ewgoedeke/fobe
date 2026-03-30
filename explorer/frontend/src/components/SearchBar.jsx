import React, { useState, useRef, useEffect } from 'react'
import { useSearch } from '../api.js'
import { Input } from './ui/input.jsx'

export default function SearchBar({ onSelect }) {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef()
  const timerRef = useRef()

  const { data: results = [] } = useSearch(debouncedQuery)

  const onChange = (e) => {
    const v = e.target.value
    setQuery(v)
    setOpen(true)
    setActiveIdx(0)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setDebouncedQuery(v), 150)
  }

  const select = (result) => {
    setQuery('')
    setDebouncedQuery('')
    setOpen(false)
    onSelect(result)
  }

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && results[activeIdx]) {
      select(results[activeIdx])
    } else if (e.key === 'Escape') {
      setOpen(false)
      inputRef.current?.blur()
    }
  }

  // Keyboard shortcut: Cmd+K or Ctrl+K
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        setOpen(true)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (!e.target.closest('[data-search]')) setOpen(false)
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [open])

  return (
    <div data-search className="relative">
      <Input
        ref={inputRef}
        placeholder="Search concepts... (\u2318K)"
        value={query}
        onChange={onChange}
        onKeyDown={onKeyDown}
        onFocus={() => setOpen(true)}
        className="w-56 h-8 text-xs"
      />
      {open && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 rounded-lg border bg-popover text-popover-foreground shadow-lg max-h-72 overflow-y-auto z-50">
          {results.map((r, i) => (
            <div
              key={r.id}
              className={`flex items-center gap-2 px-3 py-2 cursor-pointer text-sm border-b last:border-b-0 ${
                i === activeIdx ? 'bg-accent' : 'hover:bg-muted/50'
              }`}
              onClick={() => select(r)}
              onMouseEnter={() => setActiveIdx(i)}
            >
              <span
                className="inline-block w-2 h-2 rounded-full shrink-0"
                style={{ background: r.color }}
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm truncate">{r.label}</div>
                <div className="text-[10px] font-mono text-muted-foreground">{r.id}</div>
              </div>
              <span className="text-[10px] text-muted-foreground shrink-0">{r.context}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
