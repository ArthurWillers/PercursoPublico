import type { PersonSummary } from '../types/people'
import { normalizeSearch } from './financial.ts'

export interface SearchablePerson {
  person: PersonSummary
  normName: string
  normAliases: string[]
  searchHaystack: string
}

export function buildSearchablePerson(person: PersonSummary): SearchablePerson {
  const normName = normalizeSearch(person.name)
  const normAliases = person.aliases.map(alias => normalizeSearch(alias))
  const searchHaystack = ' ' + normAliases.join(' ') + ' '
  return { person, normName, normAliases, searchHaystack }
}

export function scorePerson(item: SearchablePerson, q: string): number {
  let score = 0
  let exactAlias = false
  let exactWord = false
  let phraseAlias = false
  let prefixWord = false
  let minAliasLen = 999

  for (const a of item.normAliases) {
    if (a === q) {
      exactAlias = true
      minAliasLen = Math.min(minAliasLen, a.length)
    } else if (a.includes(q)) {
      phraseAlias = true
      minAliasLen = Math.min(minAliasLen, a.length)
    }
    const words = a.split(' ')
    if (words.includes(q)) {
      exactWord = true
      minAliasLen = Math.min(minAliasLen, a.length)
    } else if (words.some(w => w.startsWith(q))) {
      prefixWord = true
      minAliasLen = Math.min(minAliasLen, a.length)
    }
  }

  if (item.normName === q || exactAlias) {
    score += 1000
  } else if (phraseAlias) {
    score += 800
  } else if (exactWord) {
    score += 700
  } else if (item.normName.startsWith(q) || prefixWord) {
    score += 500
  } else {
    score += 100
  }

  if (minAliasLen < 999) {
    score += Math.max(0, 50 - Math.min(50, minAliasLen - q.length))
  }

  const p = item.person
  if (p.offices.includes('presidente')) score += 150
  if (p.offices.includes('governador')) score += 80
  if (p.offices.includes('senador')) score += 50
  if (p.offices.includes('deputado_federal')) score += 40
  if (p.current) score += 30
  score += Math.min(p.candidacyCount * 5, 50)

  return score
}

export function filterAndRankPeople(
  items: SearchablePerson[],
  allPeople: PersonSummary[],
  query: string,
  state?: string,
  office?: string
): PersonSummary[] {
  const q = query.trim()
  const uf = state || ''
  const off = office || ''

  if (!q) {
    if (!uf && !off) return allPeople
    return allPeople.filter(person =>
      (!uf || person.states.includes(uf))
      && (!off || person.offices.some(value => value === off))
    )
  }

  const tokens = q.split(/\s+/).filter(Boolean)
  if (!tokens.length) return allPeople

  const scored: Array<{ person: PersonSummary, score: number }> = []

  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (!item) continue
    const currentPerson = item.person
    if (uf && !currentPerson.states.includes(uf)) continue
    if (off && !currentPerson.offices.some(value => value === off)) continue

    let matches = true
    for (const token of tokens) {
      if (!item.searchHaystack.includes(' ' + token)) {
        matches = false
        break
      }
    }
    if (!matches) continue

    const score = scorePerson(item, q)
    scored.push({ person: currentPerson, score })
  }

  scored.sort((a, b) => b.score - a.score || (b.person.current ? 1 : 0) - (a.person.current ? 1 : 0) || a.person.name.localeCompare(b.person.name, 'pt-BR'))
  return scored.map(s => s.person)
}
