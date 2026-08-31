import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useDebounce } from '../../hooks/useDebounce'
import { Button, Icon } from '../ui'

/**
 * Search input with dish-name typeahead.
 *
 * Suggestions come from `/autocomplete`, which does prefix matching with a fuzzy
 * fallback, so a misspelt dish name still suggests the right dish. Fully
 * keyboard navigable: arrows move, Enter accepts the highlighted suggestion or
 * submits the raw text, Escape dismisses.
 */
export function SearchBar({ value, onChange, onSubmit, loading, placeholder }) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const containerRef = useRef(null)
  const debounced = useDebounce(value, 180)

  // Fetch suggestions for the debounced term.
  useEffect(() => {
    const term = debounced.trim()
    if (term.length < 2) {
      setSuggestions([])
      return
    }

    const controller = new AbortController()
    // Named `live` rather than `active` to avoid shadowing the highlighted-index
    // state of the same name.
    let live = true

    api
      .autocomplete(term, controller.signal)
      .then((payload) => {
        if (live) {
          setSuggestions(payload.suggestions || [])
          setActive(-1)
        }
      })
      .catch(() => {
        // Typeahead is a convenience; a failure must stay silent and never
        // block the user from submitting the query they already typed.
        if (live) setSuggestions([])
      })

    return () => {
      live = false
      controller.abort()
    }
  }, [debounced])

  // Dismiss on outside click.
  useEffect(() => {
    function handlePointerDown(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [])

  const visible = open && suggestions.length > 0

  const submit = (text) => {
    setOpen(false)
    setActive(-1)
    onSubmit(text)
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Escape') {
      setOpen(false)
      setActive(-1)
      return
    }
    if (!visible) {
      if (event.key === 'Enter') submit(value)
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((current) => (current + 1) % suggestions.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((current) => (current <= 0 ? suggestions.length - 1 : current - 1))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      if (active >= 0 && suggestions[active]) {
        const chosen = suggestions[active].name
        onChange(chosen)
        submit(chosen)
      } else {
        submit(value)
      }
    }
  }

  return (
    <div className="searchbar" ref={containerRef}>
      <div className="searchbar__box">
        <Icon name="search" size={16} className="searchbar__icon" />
        <input
          className="searchbar__input"
          value={value}
          onChange={(event) => {
            onChange(event.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          aria-label="Search dishes"
          aria-autocomplete="list"
          aria-expanded={visible}
          autoComplete="off"
          spellCheck="false"
        />
        <Button
          variant="primary"
          onClick={() => submit(value)}
          disabled={loading || !value.trim()}
          loading={loading}
        >
          Search
        </Button>
      </div>

      {visible ? (
        <ul className="suggestions" role="listbox">
          {suggestions.map((suggestion, index) => (
            <li key={suggestion.name} role="option" aria-selected={index === active}>
              <button
                type="button"
                className={`suggestion ${index === active ? 'suggestion--active' : ''}`}
                onMouseEnter={() => setActive(index)}
                onClick={() => {
                  onChange(suggestion.name)
                  submit(suggestion.name)
                }}
              >
                <Icon name="search" size={12} style={{ color: 'var(--text-4)' }} />
                <span>{suggestion.name}</span>
                <span className="suggestion__meta">{suggestion.category}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
