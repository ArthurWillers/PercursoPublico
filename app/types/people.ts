import type { ElectionCandidate, ElectionOffice, Parliamentarian } from './financial'

export interface PersonSummary {
  id: string
  name: string
  aliases: string[]
  memberIds: string[]
  candidateIds: string[]
  current: boolean
  photoUrl: string | null
  years: number[]
  offices: ElectionOffice[]
  states: string[]
  candidacyCount: number
}
export interface PeopleIndex {
  schemaVersion: '1.0.0'
  coverage: Array<{ year: number, status: 'collected' | 'unavailable', linkedCandidacies: number }>
  people: PersonSummary[]
}
export interface PersonDetail {
  id: string
  name: string
  aliases: string[]
  identityBasis: 'official-cpf' | 'source-record'
  members: Parliamentarian[]
  candidacies: ElectionCandidate[]
}
