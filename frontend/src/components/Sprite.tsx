import { useState } from 'react'

// Sprites are external URLs (raw.githubusercontent.com) and some forms have none.
// Show a neutral placeholder on missing/failed images instead of a broken icon.
export function Sprite({
  url,
  name,
  className = '',
}: {
  url: string | null
  name: string
  className?: string
}) {
  const [failed, setFailed] = useState(false)
  if (!url || failed) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg bg-slate-100 text-[9px] text-slate-400 ${className}`}
      >
        no image
      </div>
    )
  }
  return (
    <img src={url} alt={name} loading="lazy" className={className} onError={() => setFailed(true)} />
  )
}
