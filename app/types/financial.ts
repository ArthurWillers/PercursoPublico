export type Chamber = 'deputados' | 'senadores'
export type ExpensePeriod = 'ano' | 'historico' | 'personalizado' | 'mandato' | 'q1' | 'q2' | 'q3' | 'q4'
export type ElectionScope = 'geral' | 'municipal'
export type ElectionOffice = 'deputado_federal' | 'senador' | 'prefeito' | 'vereador' | 'presidente' | 'governador'

export interface Mandate {
  start: string
  end: string
  partial: boolean
}
export interface Affiliation {
  start: string
  end: string | null
  party: string
}
export interface Parliamentarian {
  id: string
  name: string
  chamber: Chamber
  party: string
  state: string
  photoUrl: string | null
  sourceUrl: string
  current: boolean
  mandate: Mandate | null
  affiliations?: Affiliation[]
  otherResourcesCoverage?: Array<{ year: number, status: 'collected' | 'unavailable', sourceUrl: string, reason?: string }>
  otherResources?: Array<{ year: number, type: string, cents: number, sourceUrl: string, granularity: 'annual' }>
}
export interface SummaryRow {
  memberId: string
  year: number
  month: number
  party: string
  category: string
  inMandate: boolean
  cents: number
  count: number
}
export interface SupplierSummaryRow {
  supplierKey: string
  supplier: string
  supplierId: string
  memberId: string
  year: number
  cents: number
  count: number
}
export interface SupplierUnidentifiedRow {
  memberId: string
  year: number
  cents: number
  count: number
}
export interface AnnualSupplierSummary {
  year: number
  unidentified: SupplierUnidentifiedRow[]
  rows: SupplierSummaryRow[]
}
export interface Expense extends Omit<SummaryRow, 'count'> {
  id: string
  supplier: string
  supplierId: string | null
  issuedAt: string | null
  documentId: string | null
  documentNumber: string | null
  documentType?: string | null
  documentUrl: string | null
  portalUrl: string | null
  sourceUrl: string
  sourceRecord: string
  description?: string | null
  grossCents?: number | null
  grossAmountOriginal?: string | null
  disallowedCents?: number | null
  disallowedAmountOriginal?: string | null
  restitutionCents?: number | null
  restitutionAmountOriginal?: string | null
  restitutionAt?: string | null
  installment?: string | null
}
export interface Manifest {
  schemaVersion: string
  generatedAt: string
  years: number[]
  collectionMode: 'live' | 'cached'
  collectionPolicy?: { historicalReviewDays: number, refreshFromYear: number }
  coverage: Array<{
    chamber: Chamber
    year: number
    status: 'collected'
    ongoing: boolean
    sourceUrl: string
    fetchedAt?: string
    records: number
    cents: number
    latestMonth: number | null
    unattributed: { records: number, cents: number }
  }>
  electionYears?: number[]
  electionsCoverage?: Array<{
    year: number
    scope?: ElectionScope
    status: 'collected' | 'unavailable'
    reason?: string | null
    fetchedAt?: string | null
    sourceUrls: { candidates: string, accounts: string }
    candidacies: number
    totalRevenueCents: number
    fefcCents: number
    partyFundCents: number
    totalExpenseCents: number
  }>
  remuneration: { status: string, reason: string }
}

export interface ElectionCandidate {
  id: string
  sqCandidato: string
  year: number
  office: ElectionOffice
  name: string
  ballotName: string
  ballotNumber: string
  party: string
  state: string
  municipality?: string | null
  municipalityCode?: string | null
  result: string
  elected: boolean
  totalRevenueCents: number
  fefcCents: number
  partyFundCents: number
  individualCents: number
  ownResourcesCents: number
  otherRevenueCents: number
  revenueCount: number
  totalExpenseCents: number
  expenseCount: number
  topCategories: Array<{ category: string, cents: number, count: number }>
}

export interface ElectionAggregatedCandidateGroup {
  party: string
  office: 'vereador'
  state: string
  year: number
  candidacyCount: number
  electedCount: number
  totalRevenueCents: number
  fefcCents: number
  partyFundCents: number
  individualCents: number
  ownResourcesCents: number
  otherRevenueCents: number
  totalExpenseCents: number
  expenseCount: number
}

export interface ElectionPartySummary {
  party: string
  office: ElectionOffice
  year: number
  candidacyCount: number
  electedCount: number
  totalRevenueCents: number
  fefcCents: number
  partyFundCents: number
  individualCents: number
  ownResourcesCents: number
  otherRevenueCents: number
  totalExpenseCents: number
  expenseCount: number
}

export interface ElectionSupplierRow {
  supplierKey: string
  supplier: string
  supplierId: string
  year: number
  cents: number
  count: number
  candidacyCount: number
  offices: ElectionOffice[]
  states: string[]
  parties: string[]
  topCandidates: Array<{
    id: string
    ballotName: string
    party: string
    state: string
    municipality?: string | null
    office: ElectionOffice
    cents: number
    count: number
  }>
}

export interface ElectionYearData {
  collectedOffices?: ElectionOffice[]
  year: number
  scope?: ElectionScope
  status: 'collected' | 'unavailable'
  reason?: string | null
  fetchedAt?: string | null
  sourceUrls: { candidates: string, accounts: string }
  candidates: ElectionCandidate[]
  aggregatedCandidates?: ElectionAggregatedCandidateGroup[]
  parties: ElectionPartySummary[]
  suppliers: {
    unidentified: { cents: number, count: number }
    otherIdentified?: { cents: number, count: number, suppliers: number }
    rows: ElectionSupplierRow[]
  }
}
