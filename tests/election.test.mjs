import assert from 'node:assert/strict'
import { test } from 'node:test'
import { divulgaCandUrl } from '../app/utils/election.ts'

test('links eleitorais usam o pleito do portal, a região e a unidade eleitoral', () => {
  assert.equal(divulgaCandUrl({ year: 2026, state: 'SP', sqCandidato: '250002546642' }), 'https://divulgacandcontas.tse.jus.br/divulga/#/candidato/SUDESTE/SP/20322002026/250002546642/2026/SP')
  assert.equal(divulgaCandUrl({ year: 2026, state: 'BR', sqCandidato: '280002542548' }), 'https://divulgacandcontas.tse.jus.br/divulga/#/candidato/BR/BR/20322002026/280002542548/2026/BR')
  assert.equal(divulgaCandUrl({ year: 2010, state: 'SP', sqCandidato: '123' }), 'https://divulgacandcontas.tse.jus.br/divulga/#/home')
})
