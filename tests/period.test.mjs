import assert from 'node:assert/strict'
import { test } from 'node:test'
import { matchesPeriod, normalizeMonthRange, periodQuery, selectedYears } from '../app/utils/period.ts'
import { calculateMedianCents, cleanSupplierDigits, formatSupplierIdentifier, isValidCnpj } from '../app/utils/financial.ts'

test('intervalo por competência inclui as fronteiras e atravessa anos', () => {
  const selection = { period: 'personalizado', year: 2026, startMonth: '2019-11', endMonth: '2020-02' }
  const matches = (year, month) => matchesPeriod({ year, month, inMandate: false }, selection)
  assert.deepEqual(selectedYears(selection, [2018, 2019, 2020, 2021, 2026]), [2019, 2020])
  assert.equal(matches(2019, 10), false)
  assert.equal(matches(2019, 11), true)
  assert.equal(matches(2020, 2), true)
  assert.equal(matches(2020, 3), false)
  assert.equal(matches(2026, 1), false)
  assert.deepEqual(periodQuery(selection), { periodo: 'personalizado', inicio: '2019-11', fim: '2020-02' })
})

test('URLs inválidas ou invertidas são normalizadas aos limites publicados', () => {
  assert.deepEqual(normalizeMonthRange('2007-12', '2027-01', [2008, 2026], 2026), { startMonth: '2008-01', endMonth: '2026-12' })
  assert.deepEqual(normalizeMonthRange('2020-05', '2019-11', [2008, 2026], 2026), { startMonth: '2019-11', endMonth: '2020-05' })
  assert.deepEqual(normalizeMonthRange('2020-00', '2020-13', [2008, 2026], 2026), { startMonth: '2026-01', endMonth: '2026-12' })
  assert.deepEqual(normalizeMonthRange('2008-01', '2026-12', [2018, 2026], 2026), { startMonth: '2018-01', endMonth: '2026-12' })
})

test('ano, trimestre e mandato preservam seus próprios limites', () => {
  const selection = { period: 'q2', year: 2025, startMonth: '2008-01', endMonth: '2026-12' }
  assert.equal(matchesPeriod({ year: 2024, month: 4, inMandate: true }, selection), false)
  assert.equal(matchesPeriod({ year: 2025, month: 4, inMandate: false }, selection), true)
  assert.equal(matchesPeriod({ year: 2025, month: 7, inMandate: true }, selection), false)
  assert.equal(matchesPeriod({ year: 2010, month: 4, inMandate: false }, { ...selection, period: 'mandato' }), false)
  assert.equal(matchesPeriod({ year: 2010, month: 4, inMandate: true }, { ...selection, period: 'mandato' }), true)
})

test('identificadores de fornecedor e mediana financeira preservam invariantes', () => {
  assert.equal(cleanSupplierDigits('12.345.678/0001-99'), '12345678000199')
  assert.equal(cleanSupplierDigits('00000000000001'), null)
  assert.equal(cleanSupplierDigits('123'), null)
  assert.equal(isValidCnpj('12.345.678/0001-99'), '12345678000199')
  assert.equal(isValidCnpj('123.456.789-01'), null)
  assert.equal(formatSupplierIdentifier('12345678000199'), '12.345.678/0001-99')
  assert.equal(calculateMedianCents([]), 0)
  assert.equal(calculateMedianCents([100, 500, 200]), 200)
  assert.equal(calculateMedianCents([100, 200, 300, 400]), 250)
})
