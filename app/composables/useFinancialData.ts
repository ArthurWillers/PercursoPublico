import type { AnnualSupplierSummary, Manifest, Parliamentarian, SummaryRow } from '~/types/financial'
import { selectedYears, matchesPeriod, periodLabel as describePeriod } from '~/utils/period'
import { normalizeSearch } from '~/utils/financial'
import { fetchPublicJson } from '~/utils/fetchPublicJson'
import { publicDataUrl } from '~/utils/publicDataUrl'

export interface AggregatedSupplier {
  supplierKey: string
  supplier: string
  supplierId: string
  cents: number
  count: number
  memberCount: number
  members: Array<{
    member: Parliamentarian
    cents: number
    count: number
  }>
}

export function useFinancialData(includeSuppliers: MaybeRef<boolean> = false) {
  const baseURL = useRuntimeConfig().app.baseURL
  const manifestRequest = useFetch<Manifest>(publicDataUrl('index.json', baseURL), { server: false })
  const membersRequest = useFetch<Parliamentarian[]>(publicDataUrl('members.json', baseURL), { server: false })
  const manifest = manifestRequest.data
  const years = computed(() => manifest.value?.years ?? [])
  const defaultYear = computed(() => years.value.at(-1) ?? new Date().getFullYear())
  const { filters, resetFilters } = useExpenseFilters(defaultYear, years)
  const requestedYears = computed(() => selectedYears(filters, years.value))
  const summaryKey = computed(() => `summary:${requestedYears.value.join(',')}`)
  const summaryRequest = useAsyncData<SummaryRow[]>(summaryKey, async () => {
    const summaries = await Promise.all(requestedYears.value.map(year => fetchPublicJson<SummaryRow[]>(`summary-${year}.json`, baseURL)))
    return summaries.flat()
  }, { server: false })

  const canLoadSuppliers = computed(() => Boolean(toValue(includeSuppliers))
    && (filters.period === 'ano' || filters.period === 'historico')
    && requestedYears.value.length > 0)
  const suppliersKey = computed(() => `suppliers:${canLoadSuppliers.value ? requestedYears.value.join(',') : 'none'}`)
  const suppliersUnavailable = ref(false)
  const suppliersRequest = useAsyncData<AnnualSupplierSummary[]>(suppliersKey, async () => {
    if (!canLoadSuppliers.value) return []
    suppliersUnavailable.value = false
    try {
      return await Promise.all(requestedYears.value.map(year => fetchPublicJson<AnnualSupplierSummary>(`suppliers-${year}.json`, baseURL)))
    } catch {
      suppliersUnavailable.value = true
      return []
    }
  }, { server: false, watch: [canLoadSuppliers] })

  const error = computed(() => manifestRequest.error.value || membersRequest.error.value || summaryRequest.error.value)
  const pending = computed(() => [manifestRequest.status.value, membersRequest.status.value, summaryRequest.status.value].some(status => status === 'idle' || status === 'pending'))
  const suppliersPending = computed(() => canLoadSuppliers.value && (suppliersRequest.status.value === 'idle' || suppliersRequest.status.value === 'pending'))
  const periodTimeline = computed(() => requestedYears.value.flatMap(year => Array.from({ length: 12 }, (_, index) => ({ year, month: index + 1 }))
    .filter(row => matchesPeriod({ ...row, inMandate: false }, filters))))
  const periodLabel = computed(() => describePeriod(filters, years.value))
  const chamberMembers = computed(() => (membersRequest.data.value ?? []).filter(member => member.chamber === filters.chamber
    && (filters.status === 'todos' || member.current)))
  const baseRows = computed(() => (summaryRequest.data.value ?? []).filter(row => matchesPeriod(row, filters)))
  const partyOptions = computed(() => {
    const ids = new Set(chamberMembers.value.map(member => member.id))
    return [...new Set(baseRows.value.filter(row => ids.has(row.memberId)).map(row => row.party))].sort()
  })
  const eligibleMembers = computed(() => chamberMembers.value.filter((member) => {
    const query = normalizeSearch(filters.search)
    return (!filters.state || member.state === filters.state)
      && (!query || normalizeSearch(`${member.name} ${member.party} ${member.state}`).includes(query))
  }))
  const rows = computed(() => {
    const ids = new Set(eligibleMembers.value.map(member => member.id))
    return baseRows.value.filter(row => ids.has(row.memberId) && (!filters.party || row.party === filters.party))
  })
  const visibleMembers = computed(() => {
    const totals = new Map<string, number>()
    const counts = new Map<string, number>()
    for (const row of rows.value) {
      totals.set(row.memberId, (totals.get(row.memberId) ?? 0) + row.cents)
      counts.set(row.memberId, (counts.get(row.memberId) ?? 0) + row.count)
    }
    return eligibleMembers.value.filter(member => !filters.party || counts.has(member.id)).map(member => ({ ...member, cents: totals.get(member.id) ?? null, count: counts.get(member.id) ?? 0 }))
  })

  const globalSuppliers = computed<AggregatedSupplier[]>(() => {
    if (!canLoadSuppliers.value || !suppliersRequest.data.value?.length) return []
    const memberMap = new Map<string, Parliamentarian>()
    for (const member of chamberMembers.value) {
      if ((!filters.state || member.state === filters.state) && (!filters.party || member.party === filters.party)) {
        memberMap.set(member.id, member)
      }
    }
    const groups = new Map<string, {
      supplierKey: string
      supplier: string
      supplierId: string
      cents: number
      count: number
      byMember: Map<string, { cents: number, count: number }>
    }>()

    for (const annual of suppliersRequest.data.value) {
      for (const row of annual.rows) {
        if (!memberMap.has(row.memberId)) continue
        let group = groups.get(row.supplierKey)
        if (!group) {
          group = {
            supplierKey: row.supplierKey,
            supplier: row.supplier,
            supplierId: row.supplierId,
            cents: 0,
            count: 0,
            byMember: new Map()
          }
          groups.set(row.supplierKey, group)
        }
        group.cents += row.cents
        group.count += row.count
        const memberTotals = group.byMember.get(row.memberId) ?? { cents: 0, count: 0 }
        memberTotals.cents += row.cents
        memberTotals.count += row.count
        group.byMember.set(row.memberId, memberTotals)
      }
    }

    const query = normalizeSearch(filters.search)
    const digitsQuery = filters.search.replace(/\D/g, '')
    const result: AggregatedSupplier[] = []
    for (const group of groups.values()) {
      if (query) {
        const matchesName = normalizeSearch(`${group.supplier} ${group.supplierId}`).includes(query)
        const matchesDigits = digitsQuery.length >= 3 && group.supplierKey.includes(digitsQuery)
        if (!matchesName && !matchesDigits) continue
      }
      const members = [...group.byMember.entries()]
        .map(([id, stats]) => ({ member: memberMap.get(id)!, cents: stats.cents, count: stats.count }))
        .sort((a, b) => b.cents - a.cents)
      result.push({
        supplierKey: group.supplierKey,
        supplier: group.supplier,
        supplierId: group.supplierId,
        cents: group.cents,
        count: group.count,
        memberCount: members.length,
        members
      })
    }
    return result.sort((a, b) => b.cents - a.cents)
  })

  const unidentifiedSuppliers = computed(() => {
    if (!canLoadSuppliers.value || !suppliersRequest.data.value?.length) return { cents: 0, count: 0 }
    const eligibleIds = new Set(
      chamberMembers.value
        .filter(member => (!filters.state || member.state === filters.state) && (!filters.party || member.party === filters.party))
        .map(member => member.id)
    )
    let cents = 0
    let count = 0
    for (const annual of suppliersRequest.data.value) {
      for (const row of annual.unidentified) {
        if (!eligibleIds.has(row.memberId)) continue
        cents += row.cents
        count += row.count
      }
    }
    return { cents, count }
  })

  const coverage = computed(() => {
    const rows = manifest.value?.coverage.filter(item => item.chamber === filters.chamber
      && requestedYears.value.includes(item.year)) ?? []
    if (!rows.length) return undefined
    if (rows.length === 1) return rows[0]
    const latest = rows.at(-1)!
    return {
      ...latest,
      records: rows.reduce((sum, row) => sum + row.records, 0),
      cents: rows.reduce((sum, row) => sum + row.cents, 0),
      ongoing: rows.some(row => row.ongoing),
      unattributed: {
        records: rows.reduce((sum, row) => sum + row.unattributed.records, 0),
        cents: rows.reduce((sum, row) => sum + row.unattributed.cents, 0)
      }
    }
  })
  async function retry() {
    await Promise.all([manifestRequest.refresh(), membersRequest.refresh(), summaryRequest.refresh(), suppliersRequest.refresh()])
  }
  return {
    manifest, years, filters, resetFilters, error, pending, retry, periodTimeline, periodLabel, requestedYears,
    chamberMembers, partyOptions, rows, visibleMembers, coverage,
    globalSuppliers, unidentifiedSuppliers, suppliersPending, suppliersUnavailable
  }
}
