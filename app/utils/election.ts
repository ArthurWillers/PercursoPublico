import type { ElectionCandidate } from '../types/financial'

const portal = 'https://divulgacandcontas.tse.jus.br/divulga/#'
// IDs do DivulgaCandContas, distintos de CD_ELEICAO dos arquivos CSV.
// Conferidos na navegação oficial; consulta estadual e nacional.
const elections: Readonly<Record<number, string>> = { 2022: '2040602022', 2026: '20322002026' }
const regions: Readonly<Record<string, string>> = {
  AC: 'NORTE', AP: 'NORTE', AM: 'NORTE', PA: 'NORTE', RO: 'NORTE', RR: 'NORTE', TO: 'NORTE',
  AL: 'NORDESTE', BA: 'NORDESTE', CE: 'NORDESTE', MA: 'NORDESTE', PB: 'NORDESTE', PE: 'NORDESTE', PI: 'NORDESTE', RN: 'NORDESTE', SE: 'NORDESTE',
  DF: 'CENTROOESTE', GO: 'CENTROOESTE', MT: 'CENTROOESTE', MS: 'CENTROOESTE',
  ES: 'SUDESTE', MG: 'SUDESTE', RJ: 'SUDESTE', SP: 'SUDESTE', PR: 'SUL', RS: 'SUL', SC: 'SUL', BR: 'BR'
}

export function hasDirectElectionLink(candidate: Pick<ElectionCandidate, 'year' | 'state'>): boolean {
  return Boolean(elections[candidate.year] && regions[candidate.state])
}

export function divulgaCandUrl(candidate: Pick<ElectionCandidate, 'year' | 'state' | 'sqCandidato' | 'municipalityCode'>): string {
  const election = elections[candidate.year]
  const region = regions[candidate.state]
  if (!election || !region || !/^\d+$/.test(candidate.sqCandidato)) return `${portal}/home`
  const ue = candidate.municipalityCode || candidate.state
  return `${portal}/candidato/${region}/${candidate.state}/${election}/${candidate.sqCandidato}/${candidate.year}/${encodeURIComponent(ue)}`
}
