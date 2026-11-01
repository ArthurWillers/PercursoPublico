import type { PeopleIndex, PersonDetail } from '~/types/people'
import { fetchPublicJson } from '~/utils/fetchPublicJson'
import { normalizeSearch } from '~/utils/financial'

export function usePeopleData() {
  const route = useRoute()
  const router = useRouter()
  const baseURL = useRuntimeConfig().app.baseURL
  const indexRequest = useAsyncData('people-index', () => fetchPublicJson<PeopleIndex>('people.json', baseURL), { server: false, deep: false })
  const search = computed({
    get: () => typeof route.query.busca === 'string' ? route.query.busca : '',
    set: (value: string) => { void router.replace({ query: { ...route.query, busca: value || undefined } }) }
  })
  const people = computed(() => indexRequest.data.value?.people ?? [])
  const searchTerms = computed(() => people.value.map(person => normalizeSearch(person.aliases.join(' '))))
  const selectionRequested = computed(() => Boolean(route.query.pessoa || route.query.mandato || route.query.candidatura))
  const selectedId = computed(() => {
    if (typeof route.query.pessoa === 'string' && /^person:[a-f0-9]{32}$/.test(route.query.pessoa)) return route.query.pessoa
    if (typeof route.query.mandato === 'string') return people.value.find(person => person.memberIds.includes(String(route.query.mandato)))?.id
    if (typeof route.query.candidatura === 'string') return people.value.find(person => person.candidateIds.includes(String(route.query.candidatura)))?.id
    return undefined
  })
  const detailRequest = useAsyncData(
    () => `person:${selectedId.value ?? 'none'}`,
    async () => selectedId.value ? await fetchPublicJson<PersonDetail>(`people/${selectedId.value}.json`, baseURL) : null,
    { server: false, deep: false }
  )
  function selectPerson(id: string) {
    void router.push({ query: { ...route.query, pessoa: id, mandato: undefined, candidatura: undefined, aba: undefined, ano: undefined } })
  }
  const modalOpen = computed({
    get: () => selectionRequested.value,
    set: (open: boolean) => {
      if (!open) void router.replace({ query: { ...route.query, pessoa: undefined, mandato: undefined, candidatura: undefined, aba: undefined, ano: undefined } })
    }
  })
  return { people, searchTerms, search, selectPerson, selectedId, modalOpen, indexRequest, detailRequest }
}
