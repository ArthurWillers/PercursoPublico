<script setup lang="ts">
import { formatElectionOffice } from '~/composables/useElectionData'
import { divulgaCandUrl, hasDirectElectionLink } from '~/utils/election'
import { formatMoney, formatDate, normalizeSearch, brazilianStates } from '~/utils/financial'
import { filterAndRankPeople } from '~/utils/peopleSearch'

definePageMeta({ key: 'people-directory' })

const { people, searchIndex, search, selectPerson, selectedId, modalOpen, indexRequest, detailRequest } = usePeopleData()
const { data: indexData, status: indexStatus, error: indexError } = indexRequest
const { data: person, status: detailStatus, error: detailError } = detailRequest
const route = useRoute()
const router = useRouter()
const office = computed({
  get: () => typeof route.query.cargo === 'string' ? route.query.cargo : '',
  set: (value: string) => { void router.replace({ query: { ...route.query, cargo: value || undefined } }) }
})
const state = computed({
  get: () => typeof route.query.uf === 'string' ? route.query.uf : '',
  set: (value: string) => { void router.replace({ query: { ...route.query, uf: value || undefined } }) }
})
let personTrigger: HTMLButtonElement | null = null
function openPerson(id: string, event: MouseEvent) {
  personTrigger = event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null
  selectPerson(id)
}
function restorePersonFocus() {
  if (route.path !== '/pessoas') return
  if (personTrigger?.isConnected) personTrigger.focus()
  else document.querySelector<HTMLInputElement>('.people-search input')?.focus()
}
const page = ref(1)
const pageSize = 24
const query = computed(() => normalizeSearch(search.value))
const filteredPeople = computed(() =>
  filterAndRankPeople(searchIndex.value, people.value, query.value, state.value, office.value)
)
const pageCount = computed(() => Math.max(1, Math.ceil(filteredPeople.value.length / pageSize)))
const visiblePeople = computed(() => filteredPeople.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const view = computed({
  get: () => route.query.aba === 'eleicoes' || route.query.aba === 'mandatos' ? route.query.aba : person.value?.members.length ? 'mandatos' : 'eleicoes',
  set: (value: string) => { void router.replace({ query: { ...route.query, aba: value } }) }
})
const year = computed({
  get: () => person.value?.candidacies.some(candidate => String(candidate.year) === route.query.ano) ? String(route.query.ano) : 'todos',
  set: (value: string) => { void router.replace({ query: { ...route.query, ano: value === 'todos' ? undefined : value } }) }
})
const copied = ref(false)
const copyFailed = ref(false)
const personYears = computed(() => [...new Set(person.value?.candidacies.map(candidate => candidate.year) ?? [])].sort((a, b) => b - a))
const candidacies = computed(() => person.value?.candidacies.filter(candidate => year.value === 'todos' || candidate.year === Number(year.value)) ?? [])
const personPending = computed(() => detailStatus.value === 'pending'
  || (detailStatus.value === 'idle' && Boolean(selectedId.value))
  || (!selectedId.value && (indexStatus.value === 'pending' || indexStatus.value === 'idle')))
watch([search, office, state], () => {
  page.value = 1
})
watch([person, view, year], () => {
  copied.value = false
  copyFailed.value = false
})
const offices = [
  { value: 'presidente', label: 'Presidente' }, { value: 'governador', label: 'Governador' },
  { value: 'senador', label: 'Senador' }, { value: 'deputado_federal', label: 'Deputado Federal' },
  { value: 'prefeito', label: 'Prefeito' }, { value: 'vereador', label: 'Vereador' }
]
function clearFilters() {
  void router.replace({ query: {} })
}
async function copyLink() {
  if (!selectedId.value) return
  try {
    const url = new URL(window.location.href)
    url.search = new URLSearchParams({ pessoa: selectedId.value, aba: view.value, ...(year.value === 'todos' ? {} : { ano: year.value }) }).toString()
    await navigator.clipboard.writeText(url.href)
    copied.value = true
    copyFailed.value = false
  } catch {
    copyFailed.value = true
  }
}
useSeoMeta({ title: 'Pessoas, mandatos e histórico eleitoral', description: 'Encontre uma pessoa e consulte suas candidaturas em diferentes eleições e os gastos dos mandatos com vínculo oficial verificado.' })
</script>

<template>
  <div class="directory-page people-page">
    <header class="directory-intro">
      <h1 id="page-title">
        Encontre uma pessoa
      </h1>
      <p>Um lugar para consultar mandatos e candidaturas de diferentes anos. Comece pelo nome.</p>
    </header>

    <section
      class="people-search"
      aria-label="Buscar pessoas"
    >
      <UFormField
        label="Nome da pessoa"
        class="people-search-name"
      >
        <UInput
          v-model="search"
          icon="i-lucide-search"
          placeholder="Nome civil ou nome de urna"
          size="xl"
          class="w-full"
          type="search"
        />
      </UFormField>
      <label class="filter-field"><span>Cargo nas eleições</span>
        <select
          v-model="office"
          class="people-select"
        >
          <option value="">Todos os cargos</option>
          <option
            v-for="item in offices"
            :key="item.value"
            :value="item.value"
          >{{ item.label }}</option>
        </select>
      </label>
      <label class="filter-field"><span>Estado nos registros</span>
        <select
          v-model="state"
          class="people-select"
        >
          <option value="">Todos</option>
          <option value="BR">Brasil (presidência)</option>
          <option
            v-for="[code, name] in brazilianStates"
            :key="code"
            :value="code"
          >{{ name }}</option>
        </select>
      </label>
      <UButton
        v-if="search || office || state"
        color="neutral"
        variant="ghost"
        @click="clearFilters"
      >
        Limpar
      </UButton>
    </section>

    <div
      v-if="indexStatus === 'pending' || indexStatus === 'idle'"
      class="people-loading"
      role="status"
    >
      <p>Carregando o índice de pessoas…</p>
      <USkeleton class="h-24 w-full" /><USkeleton class="h-24 w-full" />
    </div>
    <UAlert
      v-else-if="indexError"
      title="Não foi possível carregar a busca"
      description="O índice de pessoas está indisponível. Você ainda pode consultar as despesas e as eleições pelas seções do menu."
      color="error"
      :actions="[{ label: 'Tentar novamente', onClick: () => indexRequest.refresh() }]"
    />
    <template v-else>
      <div
        class="people-result-heading"
        role="status"
      >
        <h2>{{ filteredPeople.length.toLocaleString('pt-BR') }} {{ filteredPeople.length === 1 ? 'pessoa encontrada' : 'pessoas encontradas' }}</h2>
        <span>{{ search ? 'Ordenado por relevância da busca' : 'Mandatos em exercício aparecem primeiro' }}</span>
      </div>
      <ul
        v-if="visiblePeople.length"
        class="people-list"
      >
        <li
          v-for="entry in visiblePeople"
          :key="entry.id"
        >
          <button
            type="button"
            class="people-result"
            aria-haspopup="dialog"
            @click="openPerson(entry.id, $event)"
          >
            <MemberAvatar
              :name="entry.name"
              :photo-url="entry.photoUrl"
              :photo-path="entry.photoPath"
            />
            <span class="people-result-identity">
              <strong>{{ entry.name }}</strong>
              <span>{{ entry.states.filter(Boolean).join(', ') || 'UF não informada' }} <template v-if="entry.current"> · Mandato em exercício</template></span>
              <small>{{ entry.memberIds.length ? `${entry.memberIds.length} ${entry.memberIds.length === 1 ? 'cadastro parlamentar' : 'cadastros parlamentares'} · ` : '' }}{{ entry.candidacyCount }} {{ entry.candidacyCount === 1 ? 'candidatura' : 'candidaturas' }}<template v-if="entry.years.length"> · {{ entry.years.join(', ') }}</template></small>
            </span>
            <span class="people-result-action">Abrir histórico <UIcon
              name="i-lucide-chevron-right"
              aria-hidden="true"
            /></span>
          </button>
        </li>
      </ul>
      <div
        v-else
        class="empty-state"
      >
        <UIcon
          name="i-lucide-search-x"
          aria-hidden="true"
        />
        <h2>Nenhuma pessoa neste recorte</h2>
        <p>Tente parte do nome, o nome de urna ou remova os filtros.</p>
        <UButton
          color="neutral"
          variant="outline"
          @click="clearFilters"
        >
          Limpar busca e filtros
        </UButton>
      </div>
      <div
        v-if="pageCount > 1"
        class="directory-pagination"
      >
        <UButton
          color="neutral"
          variant="outline"
          :disabled="page === 1"
          @click="page--"
        >
          Anterior
        </UButton>
        <span>Página {{ page }} de {{ pageCount }}</span>
        <UButton
          color="neutral"
          variant="outline"
          :disabled="page === pageCount"
          @click="page++"
        >
          Próxima
        </UButton>
      </div>
      <p class="people-coverage-note">
        O histórico reúne os registros já publicados neste site. Candidaturas de vereador têm cobertura individual limitada. Nomes iguais não bastam para unir pessoas. <NuxtLink to="/fontes">Entenda a cobertura e os vínculos.</NuxtLink>
      </p>
      <p
        v-if="indexData?.coverage.some(item => item.status === 'unavailable')"
        class="people-coverage-note"
      >
        Alguns pleitos estão indisponíveis na coleta. A ausência de um ano não significa que a pessoa não se candidatou.
      </p>
    </template>

    <UModal
      v-model:open="modalOpen"
      :title="person?.name ?? 'Histórico da pessoa'"
      description="Mandatos e eleições com ligação verificável nas fontes oficiais."
      :ui="{ content: 'max-w-5xl', body: 'overflow-y-auto' }"
      @after:leave="restorePersonFocus"
    >
      <template #body>
        <div
          v-if="personPending"
          role="status"
        >
          <p>Carregando histórico…</p><USkeleton class="h-40 w-full" />
        </div>
        <UAlert
          v-else-if="detailError || (indexError && !selectedId)"
          color="error"
          title="Não foi possível ler o histórico"
          :actions="[{ label: 'Tentar novamente', onClick: () => { indexRequest.refresh(); detailRequest.refresh() } }]"
        />
        <div
          v-else-if="person"
          class="person-detail"
        >
          <header class="person-context">
            <MemberAvatar
              :name="person.name"
              :photo-url="person.members.find(member => member.photoUrl)?.photoUrl ?? null"
              :photo-path="person.photoPath ?? person.candidacies.find(candidate => candidate.photoPath)?.photoPath ?? null"
            />
            <div><p>{{ person.candidacies.length }} {{ person.candidacies.length === 1 ? 'candidatura vinculada' : 'candidaturas vinculadas' }} · {{ person.members.length }} {{ person.members.length === 1 ? 'cadastro parlamentar' : 'cadastros parlamentares' }}</p><small>Campanhas e mandatos têm valores separados. Não há soma entre eleições.</small></div>
          </header>
          <UAlert
            v-if="person.identityBasis === 'source-record'"
            color="warning"
            variant="subtle"
            title="Este registro permanece separado"
            description="Ainda não há identificador compatível para ligá-lo a outros cadastros. Registros com nomes iguais podem pertencer a pessoas diferentes."
          />
          <UTabs
            v-model="view"
            :items="[{ label: 'Gastos do mandato', value: 'mandatos', icon: 'i-lucide-landmark' }, { label: `Eleições (${person.candidacies.length})`, value: 'eleicoes', icon: 'i-lucide-vote' }]"
            :content="false"
          />
          <section
            v-if="view === 'mandatos'"
            aria-label="Mandatos e acesso às despesas"
            class="person-records"
          >
            <article
              v-for="member in person.members"
              :key="member.id"
              class="person-record"
            >
              <div class="person-record-heading">
                <h3>{{ member.chamber === 'deputados' ? 'Câmara dos Deputados' : 'Senado Federal' }}</h3><UBadge
                  color="neutral"
                  variant="subtle"
                >
                  {{ member.current ? 'Em exercício' : 'Cadastro histórico' }}
                </UBadge>
              </div>
              <p>{{ member.name }} · {{ member.party }} · {{ member.state }}</p>
              <p
                v-if="member.mandate"
                class="person-record-note"
              >
                Mandato registrado: {{ formatDate(member.mandate.start) }} a {{ formatDate(member.mandate.end) }}{{ member.mandate.partial ? ' · cobertura parcial' : '' }}
              </p>
              <UButton
                :to="`/gastos/${member.id.replace(':', '-')}`"
                icon="i-lucide-receipt-text"
              >
                Consultar despesas do mandato
              </UButton>
            </article>
            <div
              v-if="!person.members.length"
              class="person-no-records"
            >
              <h3>Sem mandato vinculado neste site</h3><p>Há candidaturas eleitorais, mas nenhum cadastro parlamentar ligado por identificador verificável. Isso não afirma que a pessoa nunca exerceu um mandato.</p><UButton
                variant="outline"
                @click="view = 'eleicoes'"
              >
                Ver eleições disponíveis
              </UButton>
            </div>
          </section>
          <section
            v-else
            aria-label="Histórico de candidaturas"
            class="person-records"
          >
            <div class="person-year-filter">
              <label for="person-election-year">Eleição</label>
              <select
                id="person-election-year"
                v-model="year"
                class="people-select"
              >
                <option value="todos">
                  Todos os anos disponíveis
                </option>
                <option
                  v-for="value in personYears"
                  :key="value"
                  :value="String(value)"
                >
                  {{ value }}
                </option>
              </select>
            </div>
            <article
              v-for="candidate in candidacies"
              :key="candidate.id"
              class="person-record"
            >
              <div class="person-record-heading">
                <h3>{{ candidate.year }} · {{ formatElectionOffice(candidate.office) }}</h3>
                <div class="flex items-center gap-1.5 flex-wrap">
                  <UBadge
                    v-if="candidate.candidacyStatus && candidate.candidacyStatus.toLowerCase() !== 'apto'"
                    color="error"
                    variant="subtle"
                  >
                    {{ candidate.candidacyStatus }}: {{ candidate.candidacyDetail || 'Não concorreu' }}
                  </UBadge>
                  <UBadge
                    :color="candidate.elected ? 'primary' : 'neutral'"
                    variant="subtle"
                  >
                    {{ candidate.candidacyStatus && candidate.candidacyStatus.toLowerCase() !== 'apto' ? 'Não participou do pleito' : candidate.result }}
                  </UBadge>
                </div>
              </div>
              <p>{{ candidate.ballotName }} · {{ candidate.party }} · {{ candidate.municipality ? `${candidate.municipality} / ` : '' }}{{ candidate.state }}</p>
              <UAlert
                v-if="candidate.candidacyStatus && candidate.candidacyStatus.toLowerCase() !== 'apto'"
                color="warning"
                variant="subtle"
                title="Candidatura não participou da eleição final"
                :description="`Registro no TSE com situação '${candidate.candidacyStatus}' (${candidate.candidacyDetail || 'indeferida'}). Os valores declarados refletem a prestação de contas entregue ao TSE antes da decisão judicial ou substituição da chapa.`"
              />
              <dl class="person-election-money">
                <div><dt>Receitas declaradas</dt><dd>{{ formatMoney(candidate.totalRevenueCents) }}</dd></div><div><dt>Despesas contratadas</dt><dd>{{ formatMoney(candidate.totalExpenseCents) }}</dd></div>
              </dl>
              <details class="person-categories">
                <summary>Detalhar financiamento e despesas</summary>
                <dl class="person-funding">
                  <div><dt>Fundo Eleitoral (FEFC)</dt><dd>{{ formatMoney(candidate.fefcCents) }}</dd></div>
                  <div><dt>Fundo Partidário</dt><dd>{{ formatMoney(candidate.partyFundCents) }}</dd></div>
                  <div><dt>Pessoas físicas e financiamento coletivo</dt><dd>{{ formatMoney(candidate.individualCents) }}</dd></div>
                  <div><dt>Recursos próprios</dt><dd>{{ formatMoney(candidate.ownResourcesCents) }}</dd></div>
                  <div><dt>Outras origens de receita</dt><dd>{{ formatMoney(candidate.otherRevenueCents) }}</dd></div>
                </dl>
                <h4 v-if="candidate.topCategories.length">
                  Principais categorias de despesas
                </h4><ul class="campaign-category-list">
                  <li
                    v-for="category in candidate.topCategories"
                    :key="category.category"
                    class="campaign-category"
                  >
                    <span><strong>{{ category.category }}</strong><small>{{ category.count }} registros</small></span><span class="supplier-member-amount">{{ formatMoney(category.cents) }}</span>
                  </li>
                </ul>
              </details>
              <div class="person-record-actions">
                <UButton
                  :to="{ path: '/eleicoes', query: { ano: String(candidate.year), cargo: candidate.office, busca: candidate.ballotName, uf: candidate.state === 'BR' ? undefined : candidate.state } }"
                  color="neutral"
                  variant="outline"
                >
                  Explorar esta eleição
                </UButton><UButton
                  :to="divulgaCandUrl(candidate)"
                  target="_blank"
                  rel="noopener noreferrer"
                  color="neutral"
                  variant="ghost"
                  icon="i-lucide-external-link"
                >
                  {{ hasDirectElectionLink(candidate) ? 'Candidatura no TSE' : 'Buscar no TSE' }}
                </UButton>
              </div>
            </article>
            <div
              v-if="!candidacies.length"
              class="person-no-records"
            >
              <h3>Nenhuma candidatura vinculada</h3><p>O cadastro parlamentar está disponível, mas não foi possível ligar candidaturas com segurança nos pleitos processados.</p>
            </div>
          </section>
        </div>
        <UAlert
          v-else
          title="Pessoa não encontrada neste índice"
          description="Feche esta janela e pesquise pelo nome para localizar os registros disponíveis."
          color="warning"
        />
      </template>
      <template #footer>
        <div class="person-modal-footer">
          <UButton
            :disabled="!person"
            color="neutral"
            variant="outline"
            :icon="copied ? 'i-lucide-check' : 'i-lucide-link'"
            @click="copyLink"
          >
            {{ copied ? 'Link copiado' : 'Copiar link da pessoa' }}
          </UButton><span
            v-if="copyFailed"
            role="status"
          >Não foi possível copiar. Copie o endereço do navegador.</span><UButton
            color="neutral"
            variant="ghost"
            @click="modalOpen = false"
          >
            Fechar
          </UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
