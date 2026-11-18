import type { Expense, Manifest, Parliamentarian, SummaryRow } from '~/types/financial'
import { selectedYears, matchesPeriod, periodLabel as describePeriod } from '~/utils/period'
import { calculateMedianCents, formatDate } from '~/utils/financial'
import { fetchPublicJson } from '~/utils/fetchPublicJson'
import { publicDataUrl } from '~/utils/publicDataUrl'

export interface MandatePeriodOption {
  id: string
  label: string
  startYear: number
  endYear: number
  isPublished: boolean
}

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
  const allMemberExpenses = computed(() => expenseRequest.data.value ?? [])
  const selectedMandateId = ref('atual')
  const mandateYear = ref<number | ''>('')

  const mandateOptions = computed<MandatePeriodOption[]>(() => {
    const options: MandatePeriodOption[] = []
    const mandate = member.value?.mandate
    const publishedStartYear = mandate ? Number(mandate.start.slice(0, 4)) : null
    if (mandate && publishedStartYear !== null) {
      options.push({
        id: 'atual',
        label: `Mandato publicado (${formatDate(mandate.start)} – ${formatDate(mandate.end)})`,
        startYear: publishedStartYear,
        endYear: Number(mandate.end.slice(0, 4)),
        isPublished: true
      })
    }

    const earlierYears = [...new Set(
      allMemberExpenses.value
        .map(row => row.year)
        .filter(year => publishedStartYear === null || year < publishedStartYear)
    )].sort((a, b) => b - a)

    if (earlierYears.length) {
      if (member.value?.chamber === 'deputados') {
        const blocks: Array<[number, number]> = [
          [2019, 2022],
          [2015, 2018],
          [2011, 2014],
          [2007, 2010]
        ]
        for (const [start, end] of blocks) {
          const boundedEnd = publishedStartYear !== null ? Math.min(end, publishedStartYear - 1) : end
          if (boundedEnd < start) continue
          if (earlierYears.some(year => year >= start && year <= boundedEnd)) {
            const firstInBlock = Math.max(start, years.value[0] ?? start)
            options.push({
              id: `${firstInBlock}-${boundedEnd}`,
              label: `Registros anteriores (${firstInBlock}–${boundedEnd})`,
              startYear: firstInBlock,
              endYear: boundedEnd,
              isPublished: false
            })
          }
        }
      } else {
        const firstEarlier = earlierYears.at(-1)!
        const lastEarlier = earlierYears[0]!
        options.push({
          id: `${firstEarlier}-${lastEarlier}`,
          label: `Registros anteriores (${firstEarlier}–${lastEarlier})`,
          startYear: firstEarlier,
          endYear: lastEarlier,
          isPublished: false
        })
      }
    }

    return options
  })

  const selectedMandate = computed(() =>
    mandateOptions.value.find(option => option.id === selectedMandateId.value) ?? mandateOptions.value[0] ?? null
  )

  watch([memberId, () => filters.period], () => {
    if (filters.period !== 'mandato') {
      mandateYear.value = ''
      selectedMandateId.value = 'atual'
    }
  })
  watch(memberId, () => {
    mandateYear.value = ''
    selectedMandateId.value = 'atual'
  })
  watch(selectedMandateId, () => {
    mandateYear.value = ''
  })

  const mandateYears = computed(() => {
    if (!selectedMandate.value) return []
    return years.value.filter(year => year >= selectedMandate.value!.startYear && year <= selectedMandate.value!.endYear)
  })

  const rawExpenses = computed(() => {
    if (filters.period === 'mandato' && selectedMandate.value) {
      if (selectedMandate.value.isPublished) {
        return allMemberExpenses.value.filter(row => row.inMandate)
      }
      return allMemberExpenses.value.filter(
        row => row.year >= selectedMandate.value!.startYear && row.year <= selectedMandate.value!.endYear
      )
    }
    return allMemberExpenses.value.filter(row => matchesPeriod(row, filters))
  })
  const memberHistoryYears = computed(() => {
    const present = [...new Set(rawExpenses.value.map(row => row.year))].sort((a, b) => a - b)
    if (!present.length) return []
    const first = present[0]!
    const last = present.at(-1)!
    return years.value.filter(year => year >= first && year <= last)
  })
  const expenses = computed(() => {
    if (filters.period === 'mandato' && mandateYear.value !== '') {
      return rawExpenses.value.filter(row => row.year === mandateYear.value)
    }
    return rawExpenses.value
  })
  const periodLabel = computed(() => {
    if (filters.period === 'mandato') {
      if (selectedMandate.value && !selectedMandate.value.isPublished) {
        return `Registros ${selectedMandate.value.startYear}–${selectedMandate.value.endYear}${mandateYear.value !== '' ? ` · ${mandateYear.value}` : ''} · recorte por ano`
      }
      const base = `Mandato individual${mandateYear.value !== '' ? ` · ${mandateYear.value}` : ''}`
      return `${base}${member.value?.mandate?.partial ? ' · cobertura parcial' : ''}`
    }
    if (filters.period === 'historico') {
      return memberHistoryYears.value.length
        ? `Histórico do parlamentar · ${memberHistoryYears.value[0]}–${memberHistoryYears.value.at(-1)}`
        : 'Histórico do parlamentar · sem registros'
    }
    return describePeriod(filters, years.value)
  })
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
  return { manifest, years, filters, member, pending, error, retry, expenses, periodLabel, totalCents, requestedYears, chamberBenchmark, mandateYear, mandateYears, memberHistoryYears, mandateOptions, selectedMandateId, selectedMandate }
}
