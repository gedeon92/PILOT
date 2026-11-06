import { countryFlag } from '../countries'

/** Nom du pays précédé de son drapeau quand il est reconnu. */
export function Country({ name }: { name: string | null | undefined }) {
  if (!name) return null
  const flag = countryFlag(name)
  return (
    <span className="country">
      {flag && (
        <span className="country__flag" aria-hidden="true">
          {flag}
        </span>
      )}
      {name}
    </span>
  )
}
