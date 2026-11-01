import type { LocationQueryRaw, LocationQueryValue } from 'vue-router'
import type {
  AnnualSupplierSummary,
  ElectionAggregatedCandidateGroup,
  ElectionCandidate,
  ElectionOffice,
  ElectionPartySummary,
  ElectionScope,
  ElectionSupplierRow,
  ElectionYearData,
  Manifest,
  Parliamentarian
} from '~/types/financial'
import { normalizeSearch } from '~/utils/financial'
import { fetchPublicJson } from '~/utils/fetchPublicJson'
import { publicDataUrl } from '~/utils/publicDataUrl'

export type ElectionTab = 'candidaturas' | 'partidos' | 'fornecedores'
export type ElectionResultFilter = 'todos' | 'eleitos' | 'suplentes' | 'nao-eleitos'

export const ALL_ELECTION_YEARS = [2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, 2026] as const
export const GENERAL_ELECTION_YEARS = [2010, 2014, 2018, 2022, 2026] as const
export const MUNICIPAL_ELECTION_YEARS = [2008, 2012, 2016, 2020, 2024] as const

export function electionScopeForYear(year: number): ElectionScope {
  return (MUNICIPAL_ELECTION_YEARS as readonly number[]).includes(year) ? 'municipal' : 'geral'
}

export function defaultOfficeForYear(year: number): ElectionOffice {
  return electionScopeForYear(year) === 'municipal' ? 'prefeito' : 'deputado_federal'
}

export function isValidOfficeForYear(office: string | undefined, year: number): office is ElectionOffice {
  if (electionScopeForYear(year) === 'municipal') {
    return office === 'prefeito' || office === 'vereador'
  }
  return office === 'deputado_federal' || office === 'senador'
}

export function formatElectionOffice(office: ElectionOffice): string {
  switch (office) {
    case 'deputado_federal': return 'Deputado Federal'
    case 'senador': return 'Senador'
    case 'prefeito': return 'Prefeito'
    case 'vereador': return 'Vereador'
  }
}

export interface ElectionFilters {
  year: number
  office: ElectionOffice
  tab: ElectionTab
  result: ElectionResultFilter
  state: string
  municipality: string
  party: string
  search: string
  onlyCrossedSuppliers: boolean
}

export interface CrossedElectionSupplier extends ElectionSupplierRow {
  mandateQuota: {
    cents: number
    count: number
    memberCount: number
    members: Array<{
      member: Parliamentarian
      cents: number
      count: number
    }>
  } | null
}

function readQueryValue(value: LocationQueryValue | LocationQueryValue[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] ?? undefined : value ?? undefined
}

export function useElectionData() {
  const route = useRoute()
  const router = useRouter()
  const baseURL = useRuntimeConfig().app.baseURL

  const manifestRequest = useFetch<Manifest>(publicDataUrl('index.json', baseURL), { server: false })
  const membersRequest = useFetch<Parliamentarian[]>(publicDataUrl('members.json', baseURL), { server: false })
  const manifest = manifestRequest.data

  const electionYears = computed(() =>
    manifest.value?.electionYears?.length ? manifest.value.electionYears : [...ALL_ELECTION_YEARS]
  )
  const generalElectionYears = computed(() =>
    electionYears.value.filter(yr => electionScopeForYear(yr) === 'geral').sort((a, b) => b - a)
  )
  const municipalElectionYears = computed(() =>
    electionYears.value.filter(yr => electionScopeForYear(yr) === 'municipal').sort((a, b) => b - a)
  )
  const defaultElectionYear = computed(() => {
    const collected = manifest.value?.electionsCoverage?.filter(item => item.status === 'collected').map(item => item.year) ?? []
    return collected.at(-1) ?? 2022
  })

  const filters = reactive<ElectionFilters>({
    year: 2022,
    office: 'deputado_federal',
    tab: 'candidaturas',
    result: 'todos',
    state: '',
    municipality: '',
    party: '',
    search: '',
    onlyCrossedSuppliers: false
  })

  const currentScope = computed<ElectionScope>(() => electionScopeForYear(filters.year))

  let pendingQueryWrites = 0
  watch(
    () => [
      route.query.ano,
      route.query.cargo,
      route.query.aba,
      route.query.resultado,
      route.query.uf,
      route.query.municipio,
      route.query.partido,
      route.query.busca,
      route.query.cruzamento
    ] as const,
    ([yearVal, officeVal, tabVal, resultVal, stateVal, munVal, partyVal, searchVal, crossVal]) => {
      if (pendingQueryWrites) return
      const reqYear = Number(readQueryValue(yearVal))
      const validYear = (ALL_ELECTION_YEARS as readonly number[]).includes(reqYear) ? reqYear : defaultElectionYear.value
      const rawOffice = readQueryValue(officeVal)
      const validOffice = isValidOfficeForYear(rawOffice, validYear) ? rawOffice : defaultOfficeForYear(validYear)
      const tab = readQueryValue(tabVal)
      const result = readQueryValue(resultVal)
      const isMun = electionScopeForYear(validYear) === 'municipal'

      Object.assign(filters, {
        year: validYear,
        office: validOffice,
        tab: tab === 'partidos' || tab === 'fornecedores' ? tab : 'candidaturas',
        result: result === 'eleitos' || result === 'suplentes' || result === 'nao-eleitos' ? result : 'todos',
        state: readQueryValue(stateVal) ?? '',
        municipality: isMun ? (readQueryValue(munVal) ?? '') : '',
        party: readQueryValue(partyVal) ?? '',
        search: readQueryValue(searchVal) ?? '',
        onlyCrossedSuppliers: readQueryValue(crossVal) === 'com-cota'
      })
    },
    { immediate: true }
  )

  watch(() => filters.year, (newYear) => {
    if (!isValidOfficeForYear(filters.office, newYear)) {
      filters.office = defaultOfficeForYear(newYear)
    }
    if (electionScopeForYear(newYear) !== 'municipal') {
      filters.municipality = ''
    }
  })

  watch(() => filters.state, () => {
    filters.municipality = ''
  })

  watch(defaultElectionYear, (preferredYear) => {
    if (!route.query.ano) {
      filters.year = preferredYear
      if (!route.query.cargo) {
        filters.office = defaultOfficeForYear(preferredYear)
      }
    }
  })

  watch(filters, async (value) => {
    const query: LocationQueryRaw = { ...route.query }
    const defOffice = defaultOfficeForYear(value.year)
    query.ano = value.year === defaultElectionYear.value ? undefined : String(value.year)
    query.cargo = value.office === defOffice ? undefined : value.office
    query.aba = value.tab === 'candidaturas' ? undefined : value.tab
    query.resultado = value.result === 'todos' ? undefined : value.result
    query.uf = value.state || undefined
    query.municipio = electionScopeForYear(value.year) === 'municipal' && value.municipality ? value.municipality : undefined
    query.partido = value.party || undefined
    query.busca = value.search || undefined
    query.cruzamento = value.onlyCrossedSuppliers ? 'com-cota' : undefined

    if (JSON.stringify(query) !== JSON.stringify(route.query)) {
      pendingQueryWrites++
      try {
        await router.replace({ query })
      } finally {
        pendingQueryWrites--
      }
    }
  }, { deep: true, flush: 'post' })

  const electionRequest = useAsyncData<ElectionYearData>(
    () => `elections:${filters.year}`,
    async () => {
      try {
        return await fetchPublicJson<ElectionYearData>(`elections-${filters.year}.json`, baseURL)
      } catch {
        return {
          year: filters.year,
          scope: electionScopeForYear(filters.year),
          status: 'unavailable',
          reason: `Os arquivos normalizados da eleição de ${filters.year} ainda não constam neste snapshot publicado. Execute a coleta do pipeline para gerar elections-${filters.year}.json.`,
          fetchedAt: null,
          sourceUrls: {
            candidates: `https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_${filters.year}.zip`,
            accounts: `https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_${filters.year}.zip`
          },
          candidates: [],
          aggregatedCandidates: [],
          parties: [],
          suppliers: { unidentified: { cents: 0, count: 0 }, rows: [] }
        }
      }
    },
    { server: false, watch: [() => filters.year] }
  )

  const mandateSuppliersRequest = useAsyncData<AnnualSupplierSummary | null>(
    () => `election-mandate-suppliers:${filters.tab === 'fornecedores' ? filters.year : 'none'}`,
    async () => {
      if (filters.tab !== 'fornecedores') return null
      try {
        return await fetchPublicJson<AnnualSupplierSummary>(`suppliers-${filters.year}.json`, baseURL)
      } catch {
        return null
      }
    },
    { server: false, watch: [() => filters.tab, () => filters.year] }
  )

  const election = electionRequest.data
  const pending = computed(() => [manifestRequest.status.value, electionRequest.status.value].some(s => s === 'idle' || s === 'pending'))
  const error = computed(() => manifestRequest.error.value)

  const officeCandidates = computed(() =>
    (election.value?.candidates ?? []).filter(cand => cand.office === filters.office)
  )

  const officeAggregatedGroups = computed<ElectionAggregatedCandidateGroup[]>(() => {
    if (filters.office !== 'vereador' || filters.municipality || filters.search || filters.result !== 'todos') {
      return []
    }
    return (election.value?.aggregatedCandidates ?? []).filter(agg =>
      agg.office === 'vereador'
      && (!filters.state || agg.state === filters.state)
      && (!filters.party || agg.party === filters.party)
    )
  })

  const partyOptions = computed(() => {
    const set = new Set<string>()
    for (const cand of officeCandidates.value) set.add(cand.party)
    for (const row of election.value?.parties ?? []) {
      if (row.office === filters.office) set.add(row.party)
    }
    return [...set].sort()
  })

  const stateOptions = computed(() => {
    const set = new Set<string>()
    for (const cand of officeCandidates.value) set.add(cand.state)
    for (const agg of election.value?.aggregatedCandidates ?? []) {
      if (agg.office === filters.office) set.add(agg.state)
    }
    return set
  })

  const municipalityOptions = computed(() => {
    if (currentScope.value !== 'municipal') return []
    const set = new Set<string>()
    for (const cand of officeCandidates.value) {
      if (filters.state && cand.state !== filters.state) continue
      if (cand.municipality) set.add(cand.municipality)
    }
    return [...set].sort((a, b) => a.localeCompare(b, 'pt-BR'))
  })

  const filteredCandidates = computed<ElectionCandidate[]>(() => {
    const query = normalizeSearch(filters.search)
    return officeCandidates.value.filter((cand) => {
      if (filters.state && cand.state !== filters.state) return false
      if (filters.municipality && cand.municipality !== filters.municipality) return false
      if (filters.party && cand.party !== filters.party) return false
      if (filters.result === 'eleitos' && !cand.elected) return false
      if (filters.result === 'suplentes' && cand.result !== 'Suplente') return false
      if (filters.result === 'nao-eleitos' && (cand.elected || cand.result === 'Suplente')) return false
      if (query && !normalizeSearch(`${cand.ballotName} ${cand.name} ${cand.ballotNumber} ${cand.party} ${cand.state} ${cand.municipality ?? ''}`).includes(query)) {
        return false
      }
      return true
    })
  })

  const filteredParties = computed<ElectionPartySummary[]>(() => {
    const query = normalizeSearch(filters.search)
    if (!filters.state && !filters.municipality && filters.result === 'todos') {
      return (election.value?.parties ?? []).filter(row =>
        row.office === filters.office
        && (!filters.party || row.party === filters.party)
        && (!query || normalizeSearch(row.party).includes(query))
      )
    }
    const groups = new Map<string, ElectionPartySummary>()
    for (const cand of filteredCandidates.value) {
      let group = groups.get(cand.party)
      if (!group) {
        group = {
          party: cand.party,
          office: cand.office,
          year: cand.year,
          candidacyCount: 0,
          electedCount: 0,
          totalRevenueCents: 0,
          fefcCents: 0,
          partyFundCents: 0,
          individualCents: 0,
          ownResourcesCents: 0,
          otherRevenueCents: 0,
          totalExpenseCents: 0,
          expenseCount: 0
        }
        groups.set(cand.party, group)
      }
      group.candidacyCount++
      if (cand.elected) group.electedCount++
      group.totalRevenueCents += cand.totalRevenueCents
      group.fefcCents += cand.fefcCents
      group.partyFundCents += cand.partyFundCents
      group.individualCents += cand.individualCents
      group.ownResourcesCents += cand.ownResourcesCents
      group.otherRevenueCents += cand.otherRevenueCents
      group.totalExpenseCents += cand.totalExpenseCents
      group.expenseCount += cand.expenseCount
    }
    for (const agg of officeAggregatedGroups.value) {
      let group = groups.get(agg.party)
      if (!group) {
        group = {
          party: agg.party,
          office: agg.office,
          year: agg.year,
          candidacyCount: 0,
          electedCount: 0,
          totalRevenueCents: 0,
          fefcCents: 0,
          partyFundCents: 0,
          individualCents: 0,
          ownResourcesCents: 0,
          otherRevenueCents: 0,
          totalExpenseCents: 0,
          expenseCount: 0
        }
        groups.set(agg.party, group)
      }
      group.candidacyCount += agg.candidacyCount
      group.electedCount += agg.electedCount
      group.totalRevenueCents += agg.totalRevenueCents
      group.fefcCents += agg.fefcCents
      group.partyFundCents += agg.partyFundCents
      group.individualCents += agg.individualCents
      group.ownResourcesCents += agg.ownResourcesCents
      group.otherRevenueCents += agg.otherRevenueCents
      group.totalExpenseCents += agg.totalExpenseCents
      group.expenseCount += agg.expenseCount
    }
    return [...groups.values()].sort((a, b) => b.totalRevenueCents - a.totalRevenueCents)
  })

  const crossedSuppliers = computed<CrossedElectionSupplier[]>(() => {
    const rows = election.value?.suppliers.rows ?? []
    const memberMap = new Map<string, Parliamentarian>()
    for (const member of membersRequest.data.value ?? []) {
      memberMap.set(member.id, member)
    }

    const quotaMap = new Map<string, { cents: number, count: number, byMember: Map<string, { cents: number, count: number }> }>()
    for (const row of mandateSuppliersRequest.data.value?.rows ?? []) {
      let entry = quotaMap.get(row.supplierKey)
      if (!entry) {
        entry = { cents: 0, count: 0, byMember: new Map() }
        quotaMap.set(row.supplierKey, entry)
      }
      entry.cents += row.cents
      entry.count += row.count
      const mStats = entry.byMember.get(row.memberId) ?? { cents: 0, count: 0 }
      mStats.cents += row.cents
      mStats.count += row.count
      entry.byMember.set(row.memberId, mStats)
    }

    const query = normalizeSearch(filters.search)
    const digitsQuery = filters.search.replace(/\D/g, '')
    const result: CrossedElectionSupplier[] = []

    for (const supplier of rows) {
      if (!supplier.offices.includes(filters.office)) continue
      if (filters.state && !supplier.states.includes(filters.state)) continue
      if (filters.municipality && !supplier.topCandidates.some(c => c.municipality === filters.municipality)) continue
      if (filters.party && !supplier.parties.includes(filters.party)) continue
      if (query) {
        const matchesText = normalizeSearch(`${supplier.supplier} ${supplier.supplierId}`).includes(query)
        const matchesDigits = digitsQuery.length >= 3 && supplier.supplierKey.includes(digitsQuery)
        if (!matchesText && !matchesDigits) continue
      }

      const quota = quotaMap.get(supplier.supplierKey)
      const mandateQuota = quota
        ? {
            cents: quota.cents,
            count: quota.count,
            memberCount: quota.byMember.size,
            members: [...quota.byMember.entries()]
              .filter(([id]) => memberMap.has(id))
              .map(([id, stats]) => ({ member: memberMap.get(id)!, cents: stats.cents, count: stats.count }))
              .sort((a, b) => b.cents - a.cents)
          }
        : null

      if (filters.onlyCrossedSuppliers && !mandateQuota) continue
      result.push({ ...supplier, mandateQuota })
    }

    return result
  })

  function selectScope(scope: ElectionScope) {
    if (currentScope.value === scope) return
    const targetYears = scope === 'municipal' ? municipalElectionYears.value : generalElectionYears.value
    const nextYear = targetYears[0] ?? (scope === 'municipal' ? 2024 : 2022)
    filters.year = nextYear
    filters.office = defaultOfficeForYear(nextYear)
    filters.municipality = ''
  }

  function resetFilters() {
    Object.assign(filters, {
      year: defaultElectionYear.value,
      office: defaultOfficeForYear(defaultElectionYear.value),
      result: 'todos',
      state: '',
      municipality: '',
      party: '',
      search: '',
      onlyCrossedSuppliers: false
    })
  }

  async function retry() {
    await Promise.all([manifestRequest.refresh(), electionRequest.refresh(), mandateSuppliersRequest.refresh()])
  }

  return {
    manifest,
    electionYears,
    generalElectionYears,
    municipalElectionYears,
    currentScope,
    selectScope,
    filters,
    resetFilters,
    election,
    pending,
    error,
    retry,
    partyOptions,
    stateOptions,
    municipalityOptions,
    officeAggregatedGroups,
    filteredCandidates,
    filteredParties,
    crossedSuppliers
  }
}
