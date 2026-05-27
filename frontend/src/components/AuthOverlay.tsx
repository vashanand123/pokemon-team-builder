// Modal login/signup overlay. Rendered by App.tsx whenever `useMe()` says
// the user is unauthenticated. Two tabs — login + signup — sharing one
// username/password form. No router; the rest of the app keeps its single-
// screen design (ADR-039 + plan's modal-overlay choice).
//
// Signup mode adds a confirm-password field (purely client-side typo defense —
// the backend only takes one `password`). Username + password are deliberate
// instead of email so a reviewer can spin up multiple throwaway accounts on
// the spot without owning N inboxes (ADR-041).

import { useState } from 'react'
import { useLogin, useSignup } from '../api/auth'
import { HttpError } from '../api/client'

type Mode = 'login' | 'signup'

// Match the backend constants in `business/auth.py`.
const MIN_USERNAME_LENGTH = 3
const MAX_USERNAME_LENGTH = 32
const MIN_PASSWORD_LENGTH = 8

export function AuthOverlay() {
  const [mode, setMode] = useState<Mode>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const login = useLogin()
  const signup = useSignup()
  const busy = login.isPending || signup.isPending

  const trimmedUsername = username.trim()
  const passwordTooShort =
    mode === 'signup' && password.length > 0 && password.length < MIN_PASSWORD_LENGTH
  const passwordsMismatch =
    mode === 'signup' && confirmPassword.length > 0 && password !== confirmPassword
  // For the submit-disabled state we also require both password fields filled in signup.
  const signupIncomplete =
    mode === 'signup' && (password.length === 0 || confirmPassword.length === 0)
  const canSubmit =
    !busy &&
    trimmedUsername.length >= MIN_USERNAME_LENGTH &&
    password.length > 0 &&
    !passwordTooShort &&
    !passwordsMismatch &&
    !signupIncomplete

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    // Belt-and-suspenders: re-check passwords on submit even though `canSubmit`
    // already gates the button — keystrokes can race the click.
    if (mode === 'signup' && password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    const m = mode === 'login' ? login : signup
    try {
      await m.mutateAsync({ username: trimmedUsername, password })
      // Success: `me` invalidates, App.tsx unmounts the overlay.
    } catch (err) {
      // Surface FastAPI's `detail` string when present, else the generic message.
      if (err instanceof HttpError && err.detail) setError(err.detail)
      else setError(err instanceof Error ? err.message : 'Request failed')
    }
  }

  const switchMode = (m: Mode) => {
    setMode(m)
    setError(null)
    setConfirmPassword('')  // wipe the confirm field when leaving signup
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-bold tracking-tight">
            {mode === 'login' ? 'Sign in' : 'Create an account'}
          </h2>
          <span
            className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 text-sm"
            aria-hidden
          >
            ⚡
          </span>
        </div>

        <div className="mb-4 inline-flex rounded-lg border border-slate-200 p-0.5 text-sm">
          {(['login', 'signup'] as const).map((m) => (
            <button
              key={m}
              type="button"
              className={`rounded-md px-3 py-1 transition ${
                mode === m
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
              onClick={() => switchMode(m)}
            >
              {m === 'login' ? 'Login' : 'Sign up'}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">Username</span>
            <input
              type="text"
              autoComplete="username"
              required
              autoFocus
              minLength={MIN_USERNAME_LENGTH}
              maxLength={MAX_USERNAME_LENGTH}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            {mode === 'signup' && (
              <span className="mt-1 block text-xs text-slate-500">
                {MIN_USERNAME_LENGTH}–{MAX_USERNAME_LENGTH} characters · case-insensitive.
              </span>
            )}
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">Password</span>
            <input
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              required
              minLength={mode === 'signup' ? MIN_PASSWORD_LENGTH : 1}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            {mode === 'signup' && (
              <span
                className={`mt-1 block text-xs ${
                  passwordTooShort ? 'text-red-600' : 'text-slate-500'
                }`}
              >
                At least {MIN_PASSWORD_LENGTH} characters.
              </span>
            )}
          </label>

          {mode === 'signup' && (
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-600">
                Confirm password
              </span>
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={`w-full rounded-lg border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 ${
                  passwordsMismatch
                    ? 'border-red-400 focus:border-red-500 focus:ring-red-500'
                    : 'border-slate-300 focus:border-indigo-500 focus:ring-indigo-500'
                }`}
              />
              {passwordsMismatch && (
                <span className="mt-1 block text-xs text-red-600">
                  Passwords don&apos;t match.
                </span>
              )}
            </label>
          )}

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={!canSubmit}
            className="mt-2 w-full rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busy
              ? 'Working…'
              : mode === 'login'
                ? 'Sign in'
                : 'Create account'}
          </button>
        </form>
      </div>
    </div>
  )
}
