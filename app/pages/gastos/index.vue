<script setup lang="ts">
import { periodQuery } from '~/utils/period'
import { brazilianStates, formatMoney, formatCollectionDate, formatSupplierIdentifier } from '~/utils/financial'

const route = useRoute()
const router = useRouter()
const viewMode = computed<'parlamentares' | 'fornecedores'>({
  get: () => route.query.visao === 'fornecedores' ? 'fornecedores' : 'parlamentares',
  set: (value) => {
    const query = { ...route.query, visao: value === 'fornecedores' ? 'fornecedores' : undefined }
    router.replace({ query })
  }
})

const includeSuppliers = computed(() => viewMode.value === 'fornecedores')
const {
  manifest, years, filters, resetFilters, error, pending, retry, periodLabel,
  visibleMembers, partyOptions, globalSuppliers, unidentifiedSuppliers, suppliersPending, suppliersUnavailable
} = useFinancialData(includeSuppliers)

const order = ref('maior')
const mobileFiltersOpen = ref(false)
const page = ref(1)
const pageSize = 50
const expandedSupplierKey = ref<string | null>(null)

const secondaryFilterCount = computed(() =>
  (filters.status !== 'em-exercicio' ? 1 : 0)
  + (filters.state ? 1 : 0)
  + (filters.party ? 1 : 0)
)
const activeFilters = computed(() => filters.status !== 'em-exercicio' || filters.period !== 'ano' || Boolean(filters.search || filters.party || filters.state))

function selectChamber(chamber: 'deputados' | 'senadores') {
  filters.chamber = chamber
  filters.party = ''
  filters.state = ''
}

const members = computed(() => [...visibleMembers.value].sort((a, b) => {
  if (order.value === 'nome') return a.name.localeCompare(b.name, 'pt-BR')
  if (a.cents === null) return b.cents === null ? a.name.localeCompare(b.name) : 1
  if (b.cents === null) return -1
  return order.value === 'menor' ? a.cents - b.cents : b.cents - a.cents
}))

const maxMemberCents = computed(() => Math.max(...members.value.map(item => Math.abs(item.cents ?? 0)), 1))
const pagedMembers = computed(() => members.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const totalMemberPages = computed(() => Math.max(1, Math.ceil(members.value.length / pageSize)))

const sortedSuppliers = computed(() => {
  const list = [...globalSuppliers.value]
  if (order.value === 'nome') return list.sort((a, b) => a.supplier.localeCompare(b.supplier, 'pt-BR'))
  if (order.value === 'menor') return list.sort((a, b) => a.cents - b.cents)
  if (order.value === 'parlamentares') return list.sort((a, b) => b.memberCount - a.memberCount || b.cents - a.cents)
  return list.sort((a, b) => b.cents - a.cents)
})

const maxSupplierCents = computed(() => Math.max(...sortedSuppliers.value.map(item => Math.abs(item.cents)), 1))
const supplierPageSize = 30
const pagedSuppliers = computed(() => sortedSuppliers.value.slice((page.value - 1) * supplierPageSize, page.value * supplierPageSize))
const totalSupplierPages = computed(() => Math.max(1, Math.ceil(sortedSuppliers.value.length / supplierPageSize)))

watch([() => ({ ...filters }), viewMode, order], () => {
  page.value = 1
  expandedSupplierKey.value = null
})

const resultLabel = computed(() => {
  if (viewMode.value === 'fornecedores') {
    const count = sortedSuppliers.value.length
    return `${count.toLocaleString('pt-BR')} ${count === 1 ? 'fornecedor identificado' : 'fornecedores identificados'}`
  }
  const count = members.value.length
  const noun = filters.chamber === 'deputados' ? count === 1 ? 'deputado' : 'deputados' : count === 1 ? 'senador' : 'senadores'
  return filters.status === 'todos' ? `${count} ${count === 1 ? 'perfil' : 'perfis'} de ${noun}` : `${count} ${noun} em exercício`
})

function profileRoute(id: string, supplierKey?: string) {
  const query: Record<string, string | undefined> = { ...periodQuery(filters) }
  if (supplierKey) query.fornecedor = supplierKey
  return { path: `/gastos/${id.replace(':', '-')}`, query }
}

function toggleSupplierMembers(key: string) {
  expandedSupplierKey.value = expandedSupplierKey.value === key ? null : key
}

useSeoMeta({
  title: () => viewMode.value === 'fornecedores' ? 'Fornecedores da cota | Parlamentares' : 'Parlamentares | Gastos da cota',
  description: 'Busque perfis, fornecedores por CPF/CNPJ e consulte despesas oficiais de deputados federais e senadores.'
})
</script>

<template>
  <div class="directory-page">
    <p class="breadcrumbs">
      <NuxtLink to="/">Visão geral</NuxtLink><span aria-hidden="true">/</span> {{ viewMode === 'fornecedores' ? 'Fornecedores' : 'Parlamentares' }}
    </p>

    <DataStatus
      :pending="pending"
      :failed="Boolean(error)"
      :manifest="manifest"
      @retry="retry"
    />

    <header class="directory-intro">
      <div class="directory-intro-top">
        <div>
          <p class="intro-kicker">
            {{ viewMode === 'fornecedores' ? 'Cruzamento por CPF e CNPJ' : 'Consulta individual' }}
          </p>
          <h1 id="page-title">
            {{ viewMode === 'fornecedores' ? 'Fornecedores' : 'Parlamentares' }}
          </h1>
          <p v-if="viewMode === 'parlamentares'">
            Compare os valores publicados e abra um perfil para ver categorias, fornecedores e cobertura.
          </p>
          <p v-else>
            Consulte empresas e prestadores que receberam recursos da cota parlamentar e veja quais parlamentares contrataram cada CPF/CNPJ.
          </p>
        </div>

        <div
          class="view-mode-switch segmented-control"
          role="group"
          aria-label="Modo de consulta"
        >
          <button
            type="button"
            :aria-pressed="viewMode === 'parlamentares'"
            @click="viewMode = 'parlamentares'"
          >
            <UIcon
              name="i-lucide-users"
              aria-hidden="true"
            />
            Parlamentares
          </button>
          <button
            type="button"
            :aria-pressed="viewMode === 'fornecedores'"
            @click="viewMode = 'fornecedores'"
          >
            <UIcon
              name="i-lucide-building-2"
              aria-hidden="true"
            />
            Fornecedores
          </button>
        </div>
      </div>
    </header>

    <section
      class="directory-filters"
      aria-label="Filtros de consulta"
    >
      <div class="directory-filter-primary">
        <fieldset class="chamber-field">
          <legend>Casa legislativa</legend>
          <div class="segmented-control">
            <button
              type="button"
              :aria-pressed="filters.chamber === 'deputados'"
              @click="selectChamber('deputados')"
            >
              Deputados
            </button>
            <button
              type="button"
              :aria-pressed="filters.chamber === 'senadores'"
              @click="selectChamber('senadores')"
            >
              Senadores
            </button>
          </div>
        </fieldset>
        <label
          class="filter-field filter-collapsible"
          :class="{ 'is-open': mobileFiltersOpen || secondaryFilterCount > 0 }"
        >
          <span>Situação atual</span>
          <select v-model="filters.status">
            <option value="em-exercicio">Em exercício</option>
            <option value="todos">Todos os perfis</option>
          </select>
        </label>
        <label
          for="directory-search"
          class="filter-field"
        >
          <span>{{ viewMode === 'fornecedores' ? 'Buscar fornecedor ou CNPJ/CPF' : 'Buscar parlamentar' }}</span>
          <UInput
            id="directory-search"
            v-model="filters.search"
            icon="i-lucide-search"
            type="search"
            :placeholder="viewMode === 'fornecedores' ? 'Razão social, nome ou CNPJ/CPF' : 'Nome, partido ou estado'"
            autocomplete="off"
            class="directory-search"
            :ui="{ base: 'bg-[#FFFFFF] text-[#172C3E] placeholder:text-[#768590] dark:bg-[#FFFFFF] dark:text-[#172C3E] dark:placeholder:text-[#768590]' }"
            variant="none"
          />
        </label>
      </div>
      <div class="directory-filter-secondary">
        <label
          v-if="filters.period !== 'historico' && filters.period !== 'personalizado'"
          class="filter-field"
        >
          <span>Ano</span>
          <select v-model="filters.year">
            <option
              v-for="year in years"
              :key="year"
              :value="year"
            >{{ year }}</option>
          </select>
        </label>
        <div
          v-else
          class="filter-field"
        >
          <span>{{ filters.period === 'personalizado' ? 'Cobertura disponível' : 'Anos incluídos' }}</span>
          <span class="filter-static">{{ years[0] }}–{{ years.at(-1) }}</span>
        </div>
        <label class="filter-field">
          <span>Período</span>
          <select
            v-model="filters.period"
            aria-label="Período do ranking"
          >
            <option value="ano">Ano inteiro</option>
            <option value="historico">Histórico disponível</option>
            <option value="personalizado">Período personalizado</option>
            <option value="q1">1º trimestre</option>
            <option value="q2">2º trimestre</option>
            <option value="q3">3º trimestre</option>
            <option value="q4">4º trimestre</option>
          </select>
        </label>

        <button
          type="button"
          class="mobile-filter-toggle"
          :aria-expanded="mobileFiltersOpen || secondaryFilterCount > 0"
          @click="mobileFiltersOpen = !mobileFiltersOpen"
        >
          <UIcon
            name="i-lucide-sliders-horizontal"
            aria-hidden="true"
          />
          <span>{{ mobileFiltersOpen ? 'Ocultar filtros' : 'Estado, partido e situação' }}</span>
          <span
            v-if="secondaryFilterCount"
            class="filter-badge"
          >{{ secondaryFilterCount }}</span>
        </button>

        <label
          class="filter-field filter-collapsible"
          :class="{ 'is-open': mobileFiltersOpen || secondaryFilterCount > 0 }"
        >
          <span>{{ viewMode === 'fornecedores' ? 'Partido atual/cadastro' : 'Partido na despesa' }}</span>
          <select v-model="filters.party">
            <option value="">Todos</option>
            <option
              v-for="party in partyOptions"
              :key="party"
              :value="party"
            >{{ party }}</option>
          </select>
        </label>
        <label
          class="filter-field filter-collapsible"
          :class="{ 'is-open': mobileFiltersOpen || secondaryFilterCount > 0 }"
        >
          <span>Estado</span>
          <select v-model="filters.state">
            <option value="">Todos</option>
            <option
              v-for="[code, name] in brazilianStates"
              :key="code"
              :value="code"
            >{{ name }}</option>
          </select>
        </label>
        <UButton
          v-if="activeFilters"
          variant="ghost"
          color="neutral"
          icon="i-lucide-rotate-ccw"
          size="sm"
          @click="resetFilters"
        >
          Limpar filtros
        </UButton>
        <CustomPeriodFields
          v-if="filters.period === 'personalizado'"
          v-model:start="filters.startMonth"
          v-model:end="filters.endMonth"
          :years="years"
        />
      </div>
      <p
        v-if="manifest"
        class="directory-scope-note"
      >
        {{ filters.status === 'em-exercicio' ? 'Em exercício na última coleta.' : 'Inclui suplentes e ex-parlamentares de todo o histórico coletado.' }}
        Dados processados em {{ formatCollectionDate(manifest.generatedAt) }} (Brasília).
        O ano e o período filtram as despesas, não a situação de exercício.
      </p>
    </section>
    <p class="directory-period-note">
      {{ viewMode === 'fornecedores'
        ? 'Fornecedores agrupados exclusivamente por CPF ou CNPJ válido publicado pela fonte. Identificadores ausentes, mascarados ou técnicos permanecem separados nos perfis individuais.'
        : 'A ordenação considera somente valores publicados na mesma Casa e período; não mede eficiência. Ausência de registros não é zero. A filiação ao lado do nome vem do cadastro mais recente.' }}
    </p>

    <section
      v-if="!pending && !error && viewMode === 'parlamentares'"
      class="directory-results"
      aria-live="polite"
    >
      <header>
        <div>
          <h2>{{ resultLabel }}</h2>
          <span>{{ periodLabel }}</span>
        </div>
        <label class="directory-sort">
          <span>Ordenar por</span>
          <select v-model="order">
            <option value="maior">Maior valor</option>
            <option value="menor">Menor valor</option>
            <option value="nome">Nome A–Z</option>
          </select>
        </label>
      </header>
      <ol v-if="pagedMembers.length">
        <li
          v-for="(member, index) in pagedMembers"
          :key="member.id"
        >
          <span class="directory-rank">{{ member.cents === null || order === 'nome' ? '—' : String((page - 1) * pageSize + index + 1).padStart(2, '0') }}</span>
          <NuxtLink
            :to="profileRoute(member.id)"
            class="directory-member-link"
          >
            <MemberAvatar
              class="directory-avatar"
              :name="member.name"
              :photo-url="member.photoUrl"
            />
            <span>
              <strong>{{ member.name }}</strong>
              <small>{{ member.party }} · {{ member.state }}{{ filters.status === 'todos' ? member.current ? ' · Em exercício' : ' · Fora de exercício na coleta' : '' }}</small>
            </span>
          </NuxtLink>
          <div class="directory-amount-col">
            <span class="directory-amount">{{ member.cents === null ? 'Sem registros no recorte' : formatMoney(member.cents) }}</span>
            <div
              v-if="member.cents !== null && member.cents > 0"
              class="directory-bar-track"
              aria-hidden="true"
            >
              <span :style="{ width: `${Math.max(2, Math.min(100, (member.cents / maxMemberCents) * 100))}%` }" />
            </div>
            <small
              v-if="member.count"
              class="directory-count"
            >{{ member.count.toLocaleString('pt-BR') }} {{ member.count === 1 ? 'registro' : 'registros' }}</small>
          </div>
          <UIcon
            class="directory-arrow"
            name="i-lucide-chevron-right"
            aria-hidden="true"
          />
        </li>
      </ol>
      <div
        v-else
        class="empty-state"
      >
        <UIcon
          name="i-lucide-search-x"
          aria-hidden="true"
        />
        <h3>Nenhum resultado</h3>
        <p>Ajuste a busca ou os filtros de situação, partido e estado.</p>
      </div>

      <div
        v-if="members.length > pageSize"
        class="directory-pagination"
      >
        <UButton
          :disabled="page === 1"
          color="neutral"
          variant="outline"
          size="sm"
          @click="page--"
        >
          Anterior
        </UButton>
        <span>Mostrando {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, members.length) }} de {{ members.length }} · página {{ page }} de {{ totalMemberPages }}</span>
        <UButton
          :disabled="page >= totalMemberPages"
          color="neutral"
          variant="outline"
          size="sm"
          @click="page++"
        >
          Próxima
        </UButton>
      </div>
    </section>

    <section
      v-else-if="!pending && !error && viewMode === 'fornecedores'"
      class="directory-results"
      aria-live="polite"
    >
      <div
        v-if="filters.period !== 'ano' && filters.period !== 'historico'"
        class="empty-state"
      >
        <UIcon
          name="i-lucide-calendar-range"
          aria-hidden="true"
        />
        <h3>Granularidade anual para cruzamento de fornecedores</h3>
        <p>O agregado global de fornecedores entre parlamentares é publicado por ano ou em todo o histórico. Para filtrar fornecedores por trimestre ou intervalo de meses, abra o perfil individual do parlamentar.</p>
        <UButton
          color="primary"
          variant="solid"
          size="sm"
          @click="filters.period = 'ano'"
        >
          Mudar para Ano inteiro ({{ filters.year }})
        </UButton>
      </div>

      <p
        v-else-if="suppliersPending"
        role="status"
        class="data-status"
      >
        Carregando agregados de fornecedores…
      </p>

      <div
        v-else-if="suppliersUnavailable"
        class="empty-state"
      >
        <UIcon
          name="i-lucide-database"
          aria-hidden="true"
        />
        <h3>Índice global de fornecedores pendente de processamento</h3>
        <p>Os arquivos de fornecedores por parlamentar continuam disponíveis normalmente dentro de cada perfil.</p>
        <UButton
          color="neutral"
          variant="outline"
          size="sm"
          @click="viewMode = 'parlamentares'"
        >
          Consultar por parlamentar
        </UButton>
      </div>

      <template v-else>
        <header>
          <div>
            <h2>{{ resultLabel }}</h2>
            <span>{{ periodLabel }}</span>
          </div>
          <label class="directory-sort">
            <span>Ordenar por</span>
            <select v-model="order">
              <option value="maior">Maior valor recebido</option>
              <option value="parlamentares">Mais parlamentares</option>
              <option value="menor">Menor valor recebido</option>
              <option value="nome">Nome A–Z</option>
            </select>
          </label>
        </header>

        <ol
          v-if="pagedSuppliers.length"
          class="supplier-directory-list"
        >
          <li
            v-for="(supplier, index) in pagedSuppliers"
            :key="supplier.supplierKey"
            class="supplier-directory-item"
          >
            <div class="supplier-directory-row">
              <span class="directory-rank">{{ order === 'nome' ? '—' : String((page - 1) * supplierPageSize + index + 1).padStart(2, '0') }}</span>
              <div class="supplier-directory-info">
                <strong>{{ supplier.supplier }}</strong>
                <small>{{ formatSupplierIdentifier(supplier.supplierId) }} · {{ supplier.count.toLocaleString('pt-BR') }} {{ supplier.count === 1 ? 'registro' : 'registros' }}</small>
                <div class="supplier-directory-actions">
                  <button
                    type="button"
                    class="supplier-members-toggle"
                    :aria-expanded="expandedSupplierKey === supplier.supplierKey"
                    @click="toggleSupplierMembers(supplier.supplierKey)"
                  >
                    <UIcon
                      :name="expandedSupplierKey === supplier.supplierKey ? 'i-lucide-chevron-up' : 'i-lucide-users'"
                      aria-hidden="true"
                    />
                    <span>{{ expandedSupplierKey === supplier.supplierKey ? 'Ocultar parlamentares' : `Ver ${supplier.memberCount} ${supplier.memberCount === 1 ? 'parlamentar' : 'parlamentares'}` }}</span>
                  </button>
                  <SupplierCnpjLookup :identifier="supplier.supplierKey" />
                </div>
              </div>
              <div class="directory-amount-col">
                <span class="directory-amount">{{ formatMoney(supplier.cents) }}</span>
                <div
                  v-if="supplier.cents > 0"
                  class="directory-bar-track"
                  aria-hidden="true"
                >
                  <span :style="{ width: `${Math.max(2, Math.min(100, (supplier.cents / maxSupplierCents) * 100))}%` }" />
                </div>
                <small class="directory-count">{{ supplier.memberCount }} {{ supplier.memberCount === 1 ? 'parlamentar' : 'parlamentares' }}</small>
              </div>
            </div>

            <div
              v-if="expandedSupplierKey === supplier.supplierKey"
              class="supplier-members-drawer"
            >
              <p class="supplier-members-caption">
                Parlamentares com despesas registradas para este CPF/CNPJ no período selecionado (clique para abrir as notas no perfil):
              </p>
              <ul class="supplier-members-list">
                <li
                  v-for="entry in supplier.members"
                  :key="entry.member.id"
                >
                  <NuxtLink
                    :to="profileRoute(entry.member.id, supplier.supplierKey)"
                    class="supplier-member-chip"
                  >
                    <span>
                      <strong>{{ entry.member.name }}</strong>
                      <small>{{ entry.member.party }} · {{ entry.member.state }} ({{ entry.count }} {{ entry.count === 1 ? 'nota' : 'notas' }})</small>
                    </span>
                    <span class="supplier-member-amount">{{ formatMoney(entry.cents) }}</span>
                  </NuxtLink>
                </li>
              </ul>
            </div>
          </li>
        </ol>

        <div
          v-else
          class="empty-state"
        >
          <UIcon
            name="i-lucide-search-x"
            aria-hidden="true"
          />
          <h3>Nenhum fornecedor encontrado</h3>
          <p>Ajuste a busca por nome/CNPJ ou os filtros de estado, partido e situação.</p>
        </div>

        <p
          v-if="unidentifiedSuppliers.count > 0"
          class="supplier-unidentified-note"
        >
          Outros {{ unidentifiedSuppliers.count.toLocaleString('pt-BR') }} registros ({{ formatMoney(unidentifiedSuppliers.cents) }}) não possuem CPF/CNPJ válido ou individualizável na fonte (como gastos internacionais ou códigos internos) e permanecem separados nos perfis individuais.
        </p>

        <div
          v-if="sortedSuppliers.length > supplierPageSize"
          class="directory-pagination"
        >
          <UButton
            :disabled="page === 1"
            color="neutral"
            variant="outline"
            size="sm"
            @click="page--"
          >
            Anterior
          </UButton>
          <span>Mostrando {{ (page - 1) * supplierPageSize + 1 }}–{{ Math.min(page * supplierPageSize, sortedSuppliers.length) }} de {{ sortedSuppliers.length.toLocaleString('pt-BR') }} · página {{ page }} de {{ totalSupplierPages }}</span>
          <UButton
            :disabled="page >= totalSupplierPages"
            color="neutral"
            variant="outline"
            size="sm"
            @click="page++"
          >
            Próxima
          </UButton>
        </div>
      </template>
    </section>
  </div>
</template>
