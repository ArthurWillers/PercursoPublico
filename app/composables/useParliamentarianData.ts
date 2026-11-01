import type { Expense, Manifest, Parliamentarian, SummaryRow } from '~/types/financial'
import { selectedYears, matchesPeriod, periodLabel as describePeriod } from '~/utils/period'
import { calculateMedianCents } from '~/utils/financial'
import { fetchPublicJson } from '~/utils/fetchPublicJson'
import { publicDataUrl } from '~/utils/publicDataUrl'

export function useParliamentarianData() {
  const route = useRoute()
  const baseURL = useRuntimeConfig().app.baseURL
  const memberId = computed(() => String(route.params.id).replace(/^(camara|senado)-/, '$1:'))
  const manifestRequest = useFetch<Manifest>(publicDataUrl('index.json', baseURL), { server: false })
  const membersListRequest = useFetch<Parliamentarian[]>(publicDataUrl('members.json', baseURL), { server: false })
  const manifest = manifestRequest.data
  const years = computed(() => manifest.value?.years ?? [])
  const defaultYear = computed(() => years.value.at(-1) ?? new Date().getFullYear())
  const { filters } = useExpenseFilters(defaultYear, years, true)
  const memberRequest = useAsyncData<Parliamentarian>(
    () => `member:${memberId.value}`,
    () => fetchPublicJson<Parliamentarian>(`members/${memberId.value}.json`, baseURL),
    { server: false, watch: [memberId] }
  )
  const member = memberRequest.data
  const requestedYears = computed(() => selectedYears(filters, years.value))
  const summaryKey = computed(() => `summary:${requestedYears.value.join(',')}`)
  const summaryRequest = useAsyncData<SummaryRow[]>(
    summaryKey,
    async () => {
      if (!requestedYears.value.length) return []
      const summaries = await Promise.all(requestedYears.value.map(year => fetchPublicJson<SummaryRow[]>(`summary-${year}.json`, baseURL)))
      return summaries.flat()
    },
    { server: false }
  )
  const expenseRequest = useAsyncData<Expense[]>(
    () => `expenses:${String(route.params.id)}:${requestedYears.value.join(',')}`,
    async () => {
      if (!member.value) return []
      const files = await Promise.all(requestedYears.value.map(year => fetchPublicJson<Expense[]>(`expenses/${member.value?.id}/${year}.json`, baseURL)))
      return files.flat()
    },
    { server: false, watch: [member] }
  )
  const error = computed(() => manifestRequest.error.value || memberRequest.error.value || expenseRequest.error.value)
  const pending = computed(() => [manifestRequest.status.value, memberRequest.status.value, expenseRequest.status.value].some(status => status === 'idle' || status === 'pending'))
  const expenses = computed(() => (expenseRequest.data.value ?? []).filter(row => matchesPeriod(row, filters)))
  const periodLabel = computed(() => filters.period === 'mandato'
    ? `Mandato individual${member.value?.mandate?.partial ? ' · cobertura parcial' : ''}`
    : describePeriod(filters, years.value))
  const totalCents = computed(() => expenses.value.length ? expenses.value.reduce((sum, row) => sum + row.cents, 0) : null)

  const chamberBenchmark = computed(() => {
    if (!member.value || filters.period === 'mandato' || !summaryRequest.data.value?.length || !membersListRequest.data.value?.length) {
      return null
    }
    const targetChamber = member.value.chamber
    const eligibleIds = new Set(
      membersListRequest.data.value
        .filter(item => item.chamber === targetChamber && (item.current || !member.value?.current || item.id === member.value?.id))
        .map(item => item.id)
    )
    const totals = new Map<string, number>()
    for (const row of summaryRequest.data.value) {
      if (!eligibleIds.has(row.memberId) || !matchesPeriod(row, filters)) continue
      totals.set(row.memberId, (totals.get(row.memberId) ?? 0) + row.cents)
    }
    const values = [...totals.values()].sort((a, b) => b - a)
    if (!values.length) return null
    const sum = values.reduce((acc, val) => acc + val, 0)
    const averageCents = Math.round(sum / values.length)
    const medianCents = calculateMedianCents(values)
    const rankedIds = [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([id]) => id)
    const rankIndex = rankedIds.indexOf(member.value.id)
    return {
      averageCents,
      medianCents,
      memberCount: values.length,
      rank: rankIndex >= 0 ? rankIndex + 1 : null
    }
  })

  async function retry() {
    await manifestRequest.refresh()
    await memberRequest.refresh()
    await expenseRequest.refresh()
    await summaryRequest.refresh()
  }
  return { manifest, years, filters, member, pending, error, retry, expenses, periodLabel, totalCents, requestedYears, chamberBenchmark }
}
