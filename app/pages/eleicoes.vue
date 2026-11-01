<script setup lang="ts">
import type { ElectionCandidate } from '~/types/financial'
import { formatElectionOffice } from '~/composables/useElectionData'
import { brazilianStates, formatMoney, formatPercentage, formatSupplierIdentifier } from '~/utils/financial'

const {
  manifest,
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
} = useElectionData()

const mobileFiltersOpen = ref(false)
const candidateSort = ref<'receita' | 'fefc' | 'fp' | 'despesa' | 'nome'>('receita')
const partySort = ref<'fefc' | 'fp' | 'receita' | 'eleitos'>('fefc')
const supplierSort = ref<'campanha' | 'cota' | 'candidaturas'>('campanha')
const page = ref(1)
const pageSize = 40
const expandedCandidateId = ref<string | null>(null)
const expandedSupplierKey = ref<string | null>(null)

const secondaryFilterCount = computed(() =>
  (filters.result !== 'todos' ? 1 : 0)
  + (filters.state ? 1 : 0)
  + (filters.municipality ? 1 : 0)
  + (filters.party ? 1 : 0)
)
const activeFilters = computed(() =>
  filters.result !== 'todos'
  || Boolean(filters.state || filters.municipality || filters.party || filters.search || filters.onlyCrossedSuppliers)
)

const availableStates = computed(() =>
  stateOptions.value.size
    ? brazilianStates.filter(([code]) => stateOptions.value.has(code))
    : brazilianStates
)

const officeLabel = computed(() => formatElectionOffice(filters.office))

const aggregatedCandidacyCount = computed(() =>
  officeAggregatedGroups.value.reduce((acc, row) => acc + row.candidacyCount, 0)
)

const summaryTotals = computed(() => {
  let totalRevenue = 0
  let fefc = 0
  let partyFund = 0
  let privateAndOwn = 0
  let totalExpense = 0
  let elected = 0
  let candidacyCount = filteredCandidates.value.length
  for (const cand of filteredCandidates.value) {
    totalRevenue += cand.totalRevenueCents
    fefc += cand.fefcCents
    partyFund += cand.partyFundCents
    privateAndOwn += cand.individualCents + cand.ownResourcesCents
    totalExpense += cand.totalExpenseCents
    if (cand.elected) elected++
  }
  for (const agg of officeAggregatedGroups.value) {
    candidacyCount += agg.candidacyCount
    elected += agg.electedCount
    totalRevenue += agg.totalRevenueCents
    fefc += agg.fefcCents
    partyFund += agg.partyFundCents
    privateAndOwn += agg.individualCents + agg.ownResourcesCents
    totalExpense += agg.totalExpenseCents
  }
  const publicShare = totalRevenue > 0 ? ((fefc + partyFund) / totalRevenue) * 100 : 0
  return {
    candidacyCount,
    totalRevenue,
    fefc,
    partyFund,
    privateAndOwn,
    totalExpense,
    elected,
    publicShare
  }
})

const sortedCandidates = computed(() => {
  const list = [...filteredCandidates.value]
  if (candidateSort.value === 'nome') return list.sort((a, b) => a.ballotName.localeCompare(b.ballotName, 'pt-BR'))
  if (candidateSort.value === 'fefc') return list.sort((a, b) => b.fefcCents - a.fefcCents || b.totalRevenueCents - a.totalRevenueCents)
  if (candidateSort.value === 'fp') return list.sort((a, b) => b.partyFundCents - a.partyFundCents || b.totalRevenueCents - a.totalRevenueCents)
  if (candidateSort.value === 'despesa') return list.sort((a, b) => b.totalExpenseCents - a.totalExpenseCents)
  return list.sort((a, b) => b.totalRevenueCents - a.totalRevenueCents)
})

const pagedCandidates = computed(() => sortedCandidates.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const totalCandidatePages = computed(() => Math.max(1, Math.ceil(sortedCandidates.value.length / pageSize)))

const sortedParties = computed(() => {
  const list = [...filteredParties.value]
  if (partySort.value === 'fp') return list.sort((a, b) => b.partyFundCents - a.partyFundCents || b.fefcCents - a.fefcCents)
  if (partySort.value === 'receita') return list.sort((a, b) => b.totalRevenueCents - a.totalRevenueCents)
  if (partySort.value === 'eleitos') return list.sort((a, b) => b.electedCount - a.electedCount || b.totalRevenueCents - a.totalRevenueCents)
  return list.sort((a, b) => b.fefcCents - a.fefcCents || b.totalRevenueCents - a.totalRevenueCents)
})

const maxPartyRevenue = computed(() => Math.max(...sortedParties.value.map(item => item.totalRevenueCents), 1))

const sortedSuppliers = computed(() => {
  const list = [...crossedSuppliers.value]
  if (supplierSort.value === 'cota') {
    return list.sort((a, b) => (b.mandateQuota?.cents ?? 0) - (a.mandateQuota?.cents ?? 0) || b.cents - a.cents)
  }
  if (supplierSort.value === 'candidaturas') {
    return list.sort((a, b) => b.candidacyCount - a.candidacyCount || b.cents - a.cents)
  }
  return list.sort((a, b) => b.cents - a.cents)
})

const pagedSuppliers = computed(() => sortedSuppliers.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const totalSupplierPages = computed(() => Math.max(1, Math.ceil(sortedSuppliers.value.length / pageSize)))

watch([() => ({ ...filters }), candidateSort, partySort, supplierSort], () => {
  page.value = 1
  expandedCandidateId.value = null
  expandedSupplierKey.value = null
})

function divulgaCandUrl(cand: ElectionCandidate) {
  const ue = cand.municipalityCode || cand.state
  return `https://divulgacandcontas.tse.jus.br/divulga/#/candidato/${cand.year}/2/${ue}/${cand.sqCandidato}`
}

function mandateProfileRoute(memberId: string, year: number, supplierKey: string) {
  return {
    path: `/gastos/${memberId.replace(':', '-')}`,
    query: { ano: String(year), fornecedor: supplierKey }
  }
}

useSeoMeta({
  title: 'Eleições Gerais e Municipais (TSE) | Parlamentares',
  description: 'Consulte receitas de campanha, Fundo Eleitoral (FEFC), Fundo Partidário e fornecedores eleitorais nas eleições gerais (2010–2026) e municipais (2008–2024).'
})
</script>

<template>
  <div class="dashboard">
    <p class="breadcrumbs">
      <NuxtLink to="/">Visão geral</NuxtLink><span aria-hidden="true">/</span> Eleições e contas do TSE
    </p>

    <DataStatus
      :pending="pending"
      :failed="Boolean(error)"
      :manifest="manifest"
      @retry="retry"
    />

    <section
      class="intro"
      aria-labelledby="page-title"
    >
      <div>
        <p class="intro-kicker">
          Tribunal Superior Eleitoral (TSE) · Eleições Gerais (2010–2026) e Municipais (2008–2024)
        </p>
        <h1 id="page-title">
          Campanhas, FEFC e<br class="desktop-break"> Fundo Partidário.
        </h1>
        <p class="intro-copy">
          Prestações de contas eleitorais para Deputado Federal, Senador, Prefeito e Vereador, distribuição de fundos públicos por partido e cruzamento de fornecedores por CNPJ com a cota parlamentar.
        </p>
      </div>
      <aside class="scope-note">
        <UIcon
          name="i-lucide-scale"
          aria-hidden="true"
        />
        <p>Campanha eleitoral não é despesa de mandato. Estes valores permanecem na granularidade de candidatura e partido do TSE e nunca são somados à cota parlamentar.</p>
      </aside>
    </section>

    <section
      class="directory-filters"
      aria-label="Filtros eleitorais"
    >
      <div class="directory-filter-primary">
        <fieldset class="chamber-field">
          <legend>Âmbito e cargo em disputa</legend>
          <div class="elections-scope-row">
            <div
              class="segmented-control"
              role="group"
              aria-label="Âmbito da eleição"
            >
              <button
                type="button"
                :aria-pressed="currentScope === 'geral'"
                @click="selectScope('geral')"
              >
                Gerais (Congresso)
              </button>
              <button
                type="button"
                :aria-pressed="currentScope === 'municipal'"
                @click="selectScope('municipal')"
              >
                Municipais (Cidades)
              </button>
            </div>

            <div
              v-if="currentScope === 'geral'"
              class="segmented-control"
              role="group"
              aria-label="Cargo nas eleições gerais"
            >
              <button
                type="button"
                :aria-pressed="filters.office === 'deputado_federal'"
                @click="filters.office = 'deputado_federal'"
              >
                Deputado Federal
              </button>
              <button
                type="button"
                :aria-pressed="filters.office === 'senador'"
                @click="filters.office = 'senador'"
              >
                Senador
              </button>
            </div>

            <div
              v-else
              class="segmented-control"
              role="group"
              aria-label="Cargo nas eleições municipais"
            >
              <button
                type="button"
                :aria-pressed="filters.office === 'prefeito'"
                @click="filters.office = 'prefeito'"
              >
                Prefeito
              </button>
              <button
                type="button"
                :aria-pressed="filters.office === 'vereador'"
                @click="filters.office = 'vereador'"
              >
                Vereador
              </button>
            </div>
          </div>
        </fieldset>

        <label class="filter-field">
          <span>Ano da eleição</span>
          <select v-model.number="filters.year">
            <optgroup label="Eleições Gerais (Congresso Nacional)">
              <option
                v-for="yr in generalElectionYears"
                :key="yr"
                :value="yr"
              >
                {{ yr }} — Eleições Gerais
              </option>
            </optgroup>
            <optgroup label="Eleições Municipais (Prefeituras e Câmaras)">
              <option
                v-for="yr in municipalElectionYears"
                :key="yr"
                :value="yr"
              >
                {{ yr }} — Eleições Municipais
              </option>
            </optgroup>
          </select>
        </label>

        <label
          for="elections-search"
          class="filter-field"
        >
          <span>{{ filters.tab === 'fornecedores' ? 'Buscar fornecedor ou CNPJ/CPF' : (currentScope === 'municipal' ? 'Buscar candidatura, município, número ou partido' : 'Buscar candidatura, número ou partido') }}</span>
          <UInput
            id="elections-search"
            v-model="filters.search"
            icon="i-lucide-search"
            type="search"
            :placeholder="filters.tab === 'fornecedores' ? 'Razão social ou CNPJ/CPF' : (currentScope === 'municipal' ? 'Nome de urna, município, número ou partido' : 'Nome de urna, número, partido ou UF')"
            autocomplete="off"
            class="directory-search"
            :ui="{ base: 'bg-[#FFFFFF] text-[#172C3E] placeholder:text-[#768590] dark:bg-[#FFFFFF] dark:text-[#172C3E] dark:placeholder:text-[#768590]' }"
            variant="none"
          />
        </label>
      </div>

      <div class="directory-filter-secondary">
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
          <span>{{ mobileFiltersOpen ? 'Ocultar filtros' : (currentScope === 'municipal' ? 'Resultado, estado, município e partido' : 'Resultado, estado e partido') }}</span>
          <span
            v-if="secondaryFilterCount"
            class="filter-badge"
          >{{ secondaryFilterCount }}</span>
        </button>

        <label
          class="filter-field filter-collapsible"
          :class="{ 'is-open': mobileFiltersOpen || secondaryFilterCount > 0 }"
        >
          <span>Situação na eleição</span>
          <select v-model="filters.result">
            <option value="todos">Todas as candidaturas</option>
            <option value="eleitos">Apenas eleitos</option>
            <option value="suplentes">Suplentes</option>
            <option value="nao-eleitos">Não eleitos</option>
          </select>
        </label>

        <label
          class="filter-field filter-collapsible"
          :class="{ 'is-open': mobileFiltersOpen || secondaryFilterCount > 0 }"
        >
          <span>Estado (UF)</span>
          <select v-model="filters.state">
            <option value="">Todos</option>
            <option
              v-for="[code, name] in availableStates"
              :key="code"
              :value="code"
            >{{ name }}</option>
          </select>
        </label>

        <label
          v-if="currentScope === 'municipal'"
          class="filter-field filter-collapsible"
          :class="{ 'is-open': mobileFiltersOpen || secondaryFilterCount > 0 }"
        >
          <span>Município</span>
          <select v-model="filters.municipality">
            <option value="">Todos os municípios{{ filters.state ? ` (${filters.state})` : '' }}</option>
            <option
              v-for="mun in municipalityOptions"
              :key="mun"
              :value="mun"
            >{{ mun }}</option>
          </select>
        </label>

        <label
          class="filter-field filter-collapsible"
          :class="{ 'is-open': mobileFiltersOpen || secondaryFilterCount > 0 }"
        >
          <span>Partido</span>
          <select v-model="filters.party">
            <option value="">Todos</option>
            <option
              v-for="party in partyOptions"
              :key="party"
              :value="party"
            >{{ party }}</option>
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
      </div>
    </section>

    <div
      class="elections-tabs segmented-control"
      role="tablist"
      aria-label="Visões da prestação de contas eleitoral"
    >
      <button
        type="button"
        role="tab"
        :aria-selected="filters.tab === 'candidaturas'"
        :aria-pressed="filters.tab === 'candidaturas'"
        @click="filters.tab = 'candidaturas'"
      >
        <UIcon
          name="i-lucide-user-check"
          aria-hidden="true"
        />
        Candidaturas ({{ filteredCandidates.length.toLocaleString('pt-BR') }})
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="filters.tab === 'partidos'"
        :aria-pressed="filters.tab === 'partidos'"
        @click="filters.tab = 'partidos'"
      >
        <UIcon
          name="i-lucide-landmark"
          aria-hidden="true"
        />
        Partidos, FEFC e FP ({{ filteredParties.length }})
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="filters.tab === 'fornecedores'"
        :aria-pressed="filters.tab === 'fornecedores'"
        @click="filters.tab = 'fornecedores'"
      >
        <UIcon
          name="i-lucide-building-2"
          aria-hidden="true"
        />
        Fornecedores Campanha × Cota ({{ crossedSuppliers.length.toLocaleString('pt-BR') }})
      </button>
    </div>

    <template v-if="!pending && !error && election">
      <div
        v-if="election.status === 'unavailable'"
        class="suppliers-panel empty-state election-unavailable-card"
      >
        <UIcon
          name="i-lucide-database"
          aria-hidden="true"
        />
        <h2>Dados eleitorais de {{ filters.year }} ({{ currentScope === 'municipal' ? 'Eleições Municipais' : 'Eleições Gerais' }}) indisponíveis neste snapshot</h2>
        <p>{{ election.reason || `O pacote de prestação de contas eleitorais de ${filters.year} ainda não foi publicado ou processado.` }}</p>
        <p class="chart-caption">
          Ausência de pacote processado não significa receita ou gasto zero. Consulte diretamente os arquivos brutos no portal do TSE:
        </p>
        <div class="election-source-links">
          <a
            :href="election.sourceUrls.candidates"
            target="_blank"
            rel="noreferrer"
            class="text-link"
          >Pacote de candidaturas ({{ filters.year }}) <UIcon
            name="i-lucide-external-link"
            aria-hidden="true"
          /></a>
          <a
            :href="election.sourceUrls.accounts"
            target="_blank"
            rel="noreferrer"
            class="text-link"
          >Pacote de prestação de contas ({{ filters.year }}) <UIcon
            name="i-lucide-external-link"
            aria-hidden="true"
          /></a>
        </div>
      </div>

      <template v-else>
        <section
          id="resumo-eleitoral"
          class="summary"
          aria-label="Resumo financeiro das candidaturas selecionadas"
        >
          <article class="summary-item">
            <h2>Receitas declaradas</h2>
            <p>{{ summaryTotals.candidacyCount ? formatMoney(summaryTotals.totalRevenue) : '—' }}</p>
            <span>{{ summaryTotals.candidacyCount.toLocaleString('pt-BR') }} candidaturas · {{ summaryTotals.elected.toLocaleString('pt-BR') }} eleitos</span>
          </article>
          <article class="summary-item">
            <h2>Fundo Eleitoral (FEFC)</h2>
            <p>{{ summaryTotals.candidacyCount ? formatMoney(summaryTotals.fefc) : '—' }}</p>
            <span>{{ summaryTotals.totalRevenue ? `${formatPercentage((summaryTotals.fefc / summaryTotals.totalRevenue) * 100)} das receitas` : 'verba pública de campanha' }}</span>
          </article>
          <article class="summary-item">
            <h2>Fundo Partidário (FP)</h2>
            <p>{{ summaryTotals.candidacyCount ? formatMoney(summaryTotals.partyFund) : '—' }}</p>
            <span>{{ summaryTotals.totalRevenue ? `Fundos públicos (FEFC+FP): ${formatPercentage(summaryTotals.publicShare)}` : 'recursos partidários aplicados' }}</span>
          </article>
          <article class="summary-item">
            <h2>Pessoas físicas e próprios</h2>
            <p>{{ summaryTotals.candidacyCount ? formatMoney(summaryTotals.privateAndOwn) : '—' }}</p>
            <span>Despesas contratadas: {{ formatMoney(summaryTotals.totalExpense) }}</span>
          </article>
        </section>

        <!-- ABA 1: CANDIDATURAS -->
        <section
          v-if="filters.tab === 'candidaturas'"
          class="directory-results"
          aria-label="Candidaturas e financiamento de campanha"
        >
          <header>
            <div>
              <h2>{{ sortedCandidates.length.toLocaleString('pt-BR') }} candidaturas a {{ officeLabel }}</h2>
              <span>
                Eleições {{ currentScope === 'municipal' ? 'Municipais' : 'Gerais' }} {{ filters.year }}
                <template v-if="filters.municipality"> · {{ filters.municipality }}</template>
                · Identificador oficial SQ_CANDIDATO do TSE
              </span>
            </div>
            <label class="directory-sort">
              <span>Ordenar por</span>
              <select v-model="candidateSort">
                <option value="receita">Maior receita total</option>
                <option value="fefc">Maior Fundo Eleitoral (FEFC)</option>
                <option value="fp">Maior Fundo Partidário (FP)</option>
                <option value="despesa">Maior despesa contratada</option>
                <option value="nome">Nome de urna A–Z</option>
              </select>
            </label>
          </header>

          <p
            v-if="aggregatedCandidacyCount > 0"
            class="supplier-unidentified-note"
          >
            Para manter o carregamento ágil no navegador, outras {{ aggregatedCandidacyCount.toLocaleString('pt-BR') }} candidaturas a Vereador de menor receita estão consolidadas nos totais do resumo e na aba de Partidos/Fornecedores.
          </p>

          <ol
            v-if="pagedCandidates.length"
            class="supplier-directory-list"
          >
            <li
              v-for="(cand, idx) in pagedCandidates"
              :key="cand.id"
              class="supplier-directory-item"
            >
              <div class="supplier-directory-row">
                <span class="directory-rank">{{ candidateSort === 'nome' ? '—' : String((page - 1) * pageSize + idx + 1).padStart(2, '0') }}</span>
                <div class="supplier-directory-info">
                  <div class="election-cand-title">
                    <strong>{{ cand.ballotName }}</strong>
                    <span class="election-ballot-number">Nº {{ cand.ballotNumber }}</span>
                    <span
                      class="election-result-badge"
                      :class="{ 'is-elected': cand.elected, 'is-substitute': cand.result === 'Suplente' }"
                    >{{ cand.result }}</span>
                  </div>
                  <small>
                    {{ cand.party }} ·
                    <template v-if="cand.municipality">{{ cand.municipality }} / {{ cand.state }}</template>
                    <template v-else>{{ cand.state }}</template>
                    · Nome civil: {{ cand.name }} · ID {{ cand.id }}
                  </small>

                  <div class="election-fund-breakdown">
                    <span><strong>FEFC:</strong> {{ formatMoney(cand.fefcCents) }}</span>
                    <span><strong>Fundo Partidário:</strong> {{ formatMoney(cand.partyFundCents) }}</span>
                    <span><strong>PF / Coletivo:</strong> {{ formatMoney(cand.individualCents) }}</span>
                    <span><strong>Próprios:</strong> {{ formatMoney(cand.ownResourcesCents) }}</span>
                  </div>

                  <div class="supplier-directory-actions">
                    <button
                      v-if="cand.topCategories.length"
                      type="button"
                      class="supplier-members-toggle"
                      :aria-expanded="expandedCandidateId === cand.id"
                      @click="expandedCandidateId = expandedCandidateId === cand.id ? null : cand.id"
                    >
                      <UIcon
                        :name="expandedCandidateId === cand.id ? 'i-lucide-chevron-up' : 'i-lucide-pie-chart'"
                        aria-hidden="true"
                      />
                      <span>{{ expandedCandidateId === cand.id ? 'Ocultar despesas de campanha' : `Principais gastos (${cand.expenseCount} notas)` }}</span>
                    </button>
                    <a
                      :href="divulgaCandUrl(cand)"
                      target="_blank"
                      rel="noreferrer"
                      class="supplier-members-toggle"
                    >
                      <UIcon
                        name="i-lucide-external-link"
                        aria-hidden="true"
                      />
                      <span>Ver no DivulgaCandContas (TSE)</span>
                    </a>
                  </div>
                </div>

                <div class="directory-amount-col">
                  <span class="directory-amount">{{ formatMoney(cand.totalRevenueCents) }}</span>
                  <small class="directory-count">Despesas: {{ formatMoney(cand.totalExpenseCents) }}</small>
                </div>
              </div>

              <div
                v-if="expandedCandidateId === cand.id"
                class="supplier-members-drawer"
              >
                <p class="supplier-members-caption">
                  Principais categorias de despesas contratadas pela campanha (TSE {{ cand.year }}):
                </p>
                <ul class="supplier-members-list">
                  <li
                    v-for="cat in cand.topCategories"
                    :key="cat.category"
                  >
                    <div class="supplier-member-chip">
                      <span>
                        <strong>{{ cat.category }}</strong>
                        <small>{{ cat.count }} {{ cat.count === 1 ? 'lançamento' : 'lançamentos' }}</small>
                      </span>
                      <span class="supplier-member-amount">{{ formatMoney(cat.cents) }}</span>
                    </div>
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
            <h3>Nenhuma candidatura encontrada</h3>
            <p>Ajuste os filtros de situação, estado, município, partido ou termo de busca.</p>
          </div>

          <div
            v-if="sortedCandidates.length > pageSize"
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
            <span>Mostrando {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, sortedCandidates.length) }} de {{ sortedCandidates.length.toLocaleString('pt-BR') }} · página {{ page }} de {{ totalCandidatePages }}</span>
            <UButton
              :disabled="page >= totalCandidatePages"
              color="neutral"
              variant="outline"
              size="sm"
              @click="page++"
            >
              Próxima
            </UButton>
          </div>
        </section>

        <!-- ABA 2: PARTIDOS (FEFC e FUNDO PARTIDÁRIO) -->
        <section
          v-else-if="filters.tab === 'partidos'"
          class="suppliers-panel"
          aria-label="Distribuição por partido do Fundo Eleitoral e Fundo Partidário"
        >
          <header class="profile-panel-heading">
            <div>
              <h2>Distribuição de FEFC e Fundo Partidário por Partido</h2>
              <p>Valores aplicados nas candidaturas a {{ officeLabel }} em {{ filters.year }} ({{ currentScope === 'municipal' ? 'Eleições Municipais' : 'Eleições Gerais' }}).</p>
            </div>
            <label class="directory-sort">
              <span>Ordenar por</span>
              <select v-model="partySort">
                <option value="fefc">Maior Fundo Eleitoral (FEFC)</option>
                <option value="fp">Maior Fundo Partidário (FP)</option>
                <option value="receita">Maior receita total</option>
                <option value="eleitos">Mais eleitos</option>
              </select>
            </label>
          </header>

          <div
            v-if="sortedParties.length"
            class="supplier-table-wrap"
          >
            <table class="supplier-table">
              <thead>
                <tr>
                  <th scope="col">
                    Partido
                  </th>
                  <th scope="col">
                    Candidaturas / Eleitos
                  </th>
                  <th scope="col">
                    Fundo Eleitoral (FEFC)
                  </th>
                  <th scope="col">
                    Fundo Partidário (FP)
                  </th>
                  <th scope="col">
                    PF e Próprios
                  </th>
                  <th scope="col">
                    Receita Total
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedParties"
                  :key="`${row.party}:${row.office}`"
                >
                  <td data-label="Partido">
                    <strong>{{ row.party }}</strong>
                    <div
                      class="directory-bar-track"
                      aria-hidden="true"
                    >
                      <span :style="{ width: `${Math.max(2, Math.min(100, (row.totalRevenueCents / maxPartyRevenue) * 100))}%` }" />
                    </div>
                  </td>
                  <td data-label="Candidaturas / Eleitos">
                    <span>{{ row.candidacyCount.toLocaleString('pt-BR') }} candidaturas · <strong>{{ row.electedCount.toLocaleString('pt-BR') }} {{ row.electedCount === 1 ? 'eleito' : 'eleitos' }}</strong></span>
                  </td>
                  <td
                    class="supplier-money"
                    data-label="Fundo Eleitoral (FEFC)"
                  >
                    <span>{{ formatMoney(row.fefcCents) }}</span>
                  </td>
                  <td
                    class="supplier-money"
                    data-label="Fundo Partidário (FP)"
                  >
                    <span>{{ formatMoney(row.partyFundCents) }}</span>
                  </td>
                  <td
                    class="supplier-money"
                    data-label="PF e Próprios"
                  >
                    <span>{{ formatMoney(row.individualCents + row.ownResourcesCents) }}</span>
                  </td>
                  <td
                    class="supplier-money"
                    data-label="Receita Total"
                  >
                    <span>{{ formatMoney(row.totalRevenueCents) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p
            v-else
            class="empty-state"
          >
            Nenhum partido encontrado neste recorte.
          </p>
        </section>

        <!-- ABA 3: FORNECEDORES (CAMPANHA x COTA PARLAMENTAR) -->
        <section
          v-else-if="filters.tab === 'fornecedores'"
          class="directory-results"
          aria-label="Fornecedores de campanha e cruzamento por CNPJ com a cota parlamentar"
        >
          <header class="election-suppliers-header">
            <div>
              <h2>{{ sortedSuppliers.length.toLocaleString('pt-BR') }} fornecedores eleitorais identificados</h2>
              <span>Cruzamento exato por CPF/CNPJ entre despesas de campanha de {{ officeLabel }} (TSE {{ filters.year }}) e cota parlamentar ({{ filters.year }}). Os totais não são somados.</span>
            </div>
            <div class="election-suppliers-controls">
              <label class="cross-filter-checkbox">
                <input
                  v-model="filters.onlyCrossedSuppliers"
                  type="checkbox"
                >
                <span>Apenas fornecedores que também receberam da Cota Parlamentar</span>
              </label>
              <label class="directory-sort">
                <span>Ordenar por</span>
                <select v-model="supplierSort">
                  <option value="campanha">Maior valor na campanha (TSE)</option>
                  <option value="cota">Maior valor na cota parlamentar</option>
                  <option value="candidaturas">Mais candidaturas atendidas</option>
                </select>
              </label>
            </div>
          </header>

          <ol
            v-if="pagedSuppliers.length"
            class="supplier-directory-list"
          >
            <li
              v-for="(supplier, idx) in pagedSuppliers"
              :key="supplier.supplierKey"
              class="supplier-directory-item"
            >
              <div class="supplier-directory-row">
                <span class="directory-rank">{{ String((page - 1) * pageSize + idx + 1).padStart(2, '0') }}</span>
                <div class="supplier-directory-info">
                  <div class="election-cand-title">
                    <strong>{{ supplier.supplier }}</strong>
                    <span
                      v-if="supplier.mandateQuota"
                      class="election-crossed-badge"
                    >Recebeu na Campanha e na Cota Parlamentar</span>
                  </div>
                  <small>{{ formatSupplierIdentifier(supplier.supplierId) }} · {{ supplier.candidacyCount.toLocaleString('pt-BR') }} {{ supplier.candidacyCount === 1 ? 'candidatura' : 'candidaturas' }} ({{ supplier.count.toLocaleString('pt-BR') }} {{ supplier.count === 1 ? 'registro' : 'registros' }})</small>

                  <div class="supplier-directory-actions">
                    <button
                      type="button"
                      class="supplier-members-toggle"
                      :aria-expanded="expandedSupplierKey === supplier.supplierKey"
                      @click="expandedSupplierKey = expandedSupplierKey === supplier.supplierKey ? null : supplier.supplierKey"
                    >
                      <UIcon
                        :name="expandedSupplierKey === supplier.supplierKey ? 'i-lucide-chevron-up' : 'i-lucide-users'"
                        aria-hidden="true"
                      />
                      <span>{{ expandedSupplierKey === supplier.supplierKey ? 'Ocultar vínculos' : 'Ver candidaturas e parlamentares' }}</span>
                    </button>
                    <SupplierCnpjLookup :identifier="supplier.supplierKey" />
                  </div>
                </div>

                <div class="directory-amount-col election-dual-amounts">
                  <div class="dual-amount-item">
                    <small>Campanha (TSE {{ filters.year }})</small>
                    <span class="directory-amount">{{ formatMoney(supplier.cents) }}</span>
                  </div>
                  <div
                    v-if="supplier.mandateQuota"
                    class="dual-amount-item is-quota"
                  >
                    <small>Cota Parlamentar ({{ filters.year }})</small>
                    <span class="directory-amount">{{ formatMoney(supplier.mandateQuota.cents) }}</span>
                  </div>
                </div>
              </div>

              <div
                v-if="expandedSupplierKey === supplier.supplierKey"
                class="supplier-members-drawer"
              >
                <p class="supplier-members-caption">
                  Candidaturas que contrataram este CPF/CNPJ na campanha de {{ filters.year }}:
                </p>
                <ul class="supplier-members-list">
                  <li
                    v-for="cand in supplier.topCandidates"
                    :key="cand.id"
                  >
                    <div class="supplier-member-chip">
                      <span>
                        <strong>{{ cand.ballotName }}</strong>
                        <small>
                          {{ cand.party }} ·
                          <template v-if="cand.municipality">{{ cand.municipality }} / {{ cand.state }}</template>
                          <template v-else>{{ cand.state }}</template>
                          ({{ cand.count }} {{ cand.count === 1 ? 'nota' : 'notas' }})
                        </small>
                      </span>
                      <span class="supplier-member-amount">{{ formatMoney(cand.cents) }}</span>
                    </div>
                  </li>
                </ul>

                <template v-if="supplier.mandateQuota?.members.length">
                  <p class="supplier-members-caption quota-drawer-caption">
                    Parlamentares que pagaram este mesmo CPF/CNPJ pela Cota Parlamentar em {{ filters.year }} (clique para abrir as notas do mandato):
                  </p>
                  <ul class="supplier-members-list">
                    <li
                      v-for="entry in supplier.mandateQuota.members"
                      :key="entry.member.id"
                    >
                      <NuxtLink
                        :to="mandateProfileRoute(entry.member.id, filters.year, supplier.supplierKey)"
                        class="supplier-member-chip"
                      >
                        <span>
                          <strong>{{ entry.member.name }}</strong>
                          <small>{{ entry.member.party }} · {{ entry.member.state }} ({{ entry.count }} {{ entry.count === 1 ? 'nota' : 'notas' }} na cota)</small>
                        </span>
                        <span class="supplier-member-amount">{{ formatMoney(entry.cents) }}</span>
                      </NuxtLink>
                    </li>
                  </ul>
                </template>
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
            <h3>Nenhum fornecedor eleitoral neste recorte</h3>
            <p>Desmarque o filtro de cruzamento ou ajuste os filtros de estado, município, partido e busca.</p>
          </div>

          <p
            v-if="election.suppliers.otherIdentified && election.suppliers.otherIdentified.count > 0"
            class="supplier-unidentified-note"
          >
            Outros {{ election.suppliers.otherIdentified.suppliers.toLocaleString('pt-BR') }} fornecedores identificados de menor valor ({{ election.suppliers.otherIdentified.count.toLocaleString('pt-BR') }} registros · {{ formatMoney(election.suppliers.otherIdentified.cents) }}), sem vínculo com a cota parlamentar, estão consolidados no total da campanha.
          </p>

          <p
            v-if="election.suppliers.unidentified.count > 0"
            class="supplier-unidentified-note"
          >
            Outros {{ election.suppliers.unidentified.count.toLocaleString('pt-BR') }} registros de campanha ({{ formatMoney(election.suppliers.unidentified.cents) }}) não informam CPF/CNPJ válido na fonte do TSE e não são agrupados por fornecedor.
          </p>

          <div
            v-if="sortedSuppliers.length > pageSize"
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
            <span>Mostrando {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, sortedSuppliers.length) }} de {{ sortedSuppliers.length.toLocaleString('pt-BR') }} · página {{ page }} de {{ totalSupplierPages }}</span>
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
        </section>
      </template>
    </template>
  </div>
</template>
