/** Drapeaux des pays (CDC §13) : un repère visuel ajouté au nom du pays, jamais à sa place.
 * Le pays est saisi librement ; on reconnaît les noms français courants et les codes ISO. */

const CODES: Record<string, string> = {
  // Afrique
  'afrique du sud': 'ZA',
  algerie: 'DZ',
  angola: 'AO',
  benin: 'BJ',
  botswana: 'BW',
  'burkina faso': 'BF',
  burkina: 'BF',
  burundi: 'BI',
  cameroun: 'CM',
  'cap-vert': 'CV',
  'cap vert': 'CV',
  centrafrique: 'CF',
  'republique centrafricaine': 'CF',
  comores: 'KM',
  congo: 'CG',
  'congo-brazzaville': 'CG',
  'republique du congo': 'CG',
  rdc: 'CD',
  'rd congo': 'CD',
  'congo-kinshasa': 'CD',
  'republique democratique du congo': 'CD',
  "cote d'ivoire": 'CI',
  'cote divoire': 'CI',
  'cote d ivoire': 'CI',
  djibouti: 'DJ',
  egypte: 'EG',
  erythree: 'ER',
  eswatini: 'SZ',
  ethiopie: 'ET',
  gabon: 'GA',
  gambie: 'GM',
  ghana: 'GH',
  guinee: 'GN',
  'guinee-bissau': 'GW',
  'guinee equatoriale': 'GQ',
  kenya: 'KE',
  lesotho: 'LS',
  liberia: 'LR',
  libye: 'LY',
  madagascar: 'MG',
  malawi: 'MW',
  mali: 'ML',
  maroc: 'MA',
  maurice: 'MU',
  mauritanie: 'MR',
  mozambique: 'MZ',
  namibie: 'NA',
  niger: 'NE',
  nigeria: 'NG',
  ouganda: 'UG',
  rwanda: 'RW',
  'sao tome-et-principe': 'ST',
  senegal: 'SN',
  seychelles: 'SC',
  'sierra leone': 'SL',
  somalie: 'SO',
  soudan: 'SD',
  'soudan du sud': 'SS',
  tanzanie: 'TZ',
  tchad: 'TD',
  togo: 'TG',
  tunisie: 'TN',
  zambie: 'ZM',
  zimbabwe: 'ZW',
  // Europe
  allemagne: 'DE',
  autriche: 'AT',
  belgique: 'BE',
  danemark: 'DK',
  espagne: 'ES',
  finlande: 'FI',
  france: 'FR',
  grece: 'GR',
  irlande: 'IE',
  italie: 'IT',
  luxembourg: 'LU',
  monaco: 'MC',
  norvege: 'NO',
  'pays-bas': 'NL',
  'pays bas': 'NL',
  pologne: 'PL',
  portugal: 'PT',
  'royaume-uni': 'GB',
  'royaume uni': 'GB',
  suede: 'SE',
  suisse: 'CH',
  // Amériques, Asie, Moyen-Orient
  bresil: 'BR',
  canada: 'CA',
  'etats-unis': 'US',
  'etats unis': 'US',
  usa: 'US',
  haiti: 'HT',
  mexique: 'MX',
  chine: 'CN',
  inde: 'IN',
  japon: 'JP',
  'arabie saoudite': 'SA',
  'emirats arabes unis': 'AE',
  emirats: 'AE',
  liban: 'LB',
  qatar: 'QA',
  turquie: 'TR',
}

function fold(text: string) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[’`]/g, "'").trim().toLowerCase()
}

/** Code ISO à deux lettres, ou null si le pays n'est pas reconnu. */
export function countryCode(country: string | null | undefined): string | null {
  if (!country) return null
  const key = fold(country)
  if (CODES[key]) return CODES[key]
  if (/^[a-z]{2}$/.test(key)) return key.toUpperCase()
  return null
}

/** Drapeau emoji du pays, ou chaîne vide si le pays n'est pas reconnu. */
export function countryFlag(country: string | null | undefined): string {
  const code = countryCode(country)
  if (!code) return ''
  return String.fromCodePoint(...[...code].map((c) => 0x1f1a5 + c.charCodeAt(0)))
}
