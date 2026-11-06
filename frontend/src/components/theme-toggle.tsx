import { useTheme } from '../theme'
import { MoonIcon, SunIcon } from './icons'

/** Bascule entre le mode sombre et le mode clair. */
export function ThemeToggle({ className = 'nav__link' }: { className?: string }) {
  const [theme, setTheme] = useTheme()
  const light = theme === 'light'
  return (
    <button
      type="button"
      className={className}
      aria-pressed={light}
      onClick={() => setTheme(light ? 'dark' : 'light')}
    >
      {light ? <MoonIcon /> : <SunIcon />}
      <span className="nav__label">{light ? 'Mode sombre' : 'Mode clair'}</span>
    </button>
  )
}
