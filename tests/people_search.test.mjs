import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildSearchablePerson, filterAndRankPeople } from '../app/utils/peopleSearch.ts'

const peopleFixture = [
  {
    id: 'person:lula',
    name: 'LULA',
    aliases: ['LUIZ INÁCIO LULA DA SILVA', 'LULA'],
    memberIds: [],
    candidateIds: ['tse:2022:1', 'tse:2026:1'],
    current: false,
    photoUrl: null,
    years: [2026, 2022],
    offices: ['presidente'],
    states: ['BR'],
    candidacyCount: 2
  },
  {
    id: 'person:gleisi',
    name: 'Gleisi Hoffmann',
    aliases: ['GLEISI', 'GLEISI HELENA HOFFMANN', 'GLEISI LULA', 'Gleisi Hoffmann'],
    memberIds: ['camara:1001'],
    candidateIds: ['tse:2022:2'],
    current: true,
    photoUrl: 'https://camara.leg.br/foto.jpg',
    years: [2022],
    offices: ['deputado_federal'],
    states: ['PR'],
    candidacyCount: 1
  },
  {
    id: 'person:celular',
    name: 'BAHIA DO CELULAR',
    aliases: ['BAHIA DO CELULAR', 'JOSE BAHIA'],
    memberIds: [],
    candidateIds: ['tse:2020:3'],
    current: false,
    photoUrl: null,
    years: [2020],
    offices: ['vereador'],
    states: ['SP'],
    candidacyCount: 1
  },
  {
    id: 'person:lula-fonte',
    name: 'Lula da Fonte',
    aliases: ['LULA DA FONTE', 'EDUARDO DA FONTE FILHO'],
    memberIds: ['camara:1002'],
    candidateIds: ['tse:2022:4'],
    current: true,
    photoUrl: 'https://camara.leg.br/fonte.jpg',
    years: [2022],
    offices: ['deputado_federal'],
    states: ['PE'],
    candidacyCount: 1
  }
]

const searchIndex = peopleFixture.map(buildSearchablePerson)

test('busca por LULA nunca inclui falsos positivos por substring dentro de palavras como CELULAR', () => {
  const results = filterAndRankPeople(searchIndex, peopleFixture, 'lula')
  const ids = results.map(p => p.id)

  assert.ok(ids.includes('person:lula'))
  assert.ok(ids.includes('person:gleisi'))
  assert.ok(ids.includes('person:lula-fonte'))
  assert.ok(!ids.includes('person:celular'), 'Bahia do Celular não deve ser retornado na busca por LULA')
})

test('busca por LULA classifica Luiz Inácio Lula da Silva como primeiro colocado', () => {
  const results = filterAndRankPeople(searchIndex, peopleFixture, 'lula')
  assert.equal(results[0]?.id, 'person:lula')
})

test('busca por múltiplos termos exige correspondência de todos os termos', () => {
  const results = filterAndRankPeople(searchIndex, peopleFixture, 'lula silva')
  assert.equal(results.length, 1)
  assert.equal(results[0]?.id, 'person:lula')
})

test('filtros de estado e cargo refinam os resultados', () => {
  const resultsPE = filterAndRankPeople(searchIndex, peopleFixture, 'lula', 'PE')
  assert.equal(resultsPE.length, 1)
  assert.equal(resultsPE[0]?.id, 'person:lula-fonte')

  const resultsPres = filterAndRankPeople(searchIndex, peopleFixture, 'lula', undefined, 'presidente')
  assert.equal(resultsPres.length, 1)
  assert.equal(resultsPres[0]?.id, 'person:lula')
})
