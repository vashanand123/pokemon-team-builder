// A tiny shared button "system" so accent / hover / active / focus stay consistent.
// Callers append sizing (px/py/text-size) so existing layouts don't shift.
const base =
  'inline-flex items-center justify-center gap-1 rounded-lg font-medium transition ' +
  'active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 ' +
  'disabled:pointer-events-none disabled:opacity-50'

export const btnPrimary = `${base} bg-indigo-600 text-white shadow-sm hover:bg-indigo-700 focus-visible:ring-indigo-500`
export const btnSecondary = `${base} border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 focus-visible:ring-slate-400`
export const btnDanger = `${base} border border-red-200 bg-white text-red-600 hover:bg-red-50 focus-visible:ring-red-400`
