<script setup lang="ts">
import { periodQuery } from '~/utils/period'
import { brazilianStates, months, categoryColors, formatMoney, formatCompactMoney, calculateMedianCents } from '~/utils/financial'

const { manifest, years, filters, resetFilters, error, pending, retry, periodTimeline, periodLabel, requestedYears,
  chamberMembers, partyOptions, rows, visibleMembers: allMembers, coverage } = useFinancialData()
const periods = [
  { value: 'ano', label: 'Ano inteiro' },
  { value: 'historico', label: 'Histórico disponível' },
  { value: 'personalizado', label: 'Período personalizado' },
  { value: 'q1', label: '1º trimestre' }, { value: 'q2', label: '2º trimestre' },
  { value: 'q3', label: '3º trimestre' }, { value: 'q4', label: '4º trimestre' }
]
const mobileFiltersOpen = ref(false)
const secondaryFilterCount = computed(() =>
  (filters.status !== 'em-exercicio' ? 1 : 0)
  + (filters.state ? 1 : 0)
  + (filters.party ? 1 : 0)
)
const visibleMembers = computed(() => allMembers.value.filter(member => member.cents !== null)
  .map(member => ({ ...member, cents: member.cents ?? 0 })))
const stateOptions = computed(() => {
  const codes = new Set(chamberMembers.value.map(member => member.state))
  return brazilianStates.filter(([code]) => codes.has(code))
})
const trendItems = computed(() => filters.period === 'historico'
  ? years.value.map((year) => {
      const yearRows = rows.value.filter(row => row.year === year)
      return { key: String(year), label: String(year), cents: yearRows.reduce((sum, row) => sum + row.cents, 0), count: yearRows.reduce((sum, row) => sum + row.count, 0) }
    })
  : periodTimeline.value.map(({ year, month }) => {
      const monthRows = rows.value.filter(row => row.month === month && row.year === year)
      return { key: `${year}-${month}`, label: `${months[month - 1]}${filters.period === 'personalizado' ? ` ${year}` : ''}`, cents: monthRows.reduce((sum, row) => sum + row.cents, 0), count: monthRows.reduce((sum, row) => sum + row.count, 0) }
    }))
const totalCents = computed(() => rows.value.reduce((sum, row) => sum + row.cents, 0))
const maximumTrendTotal = computed(() => Math.max(...trendItems.value.map(item => Math.abs(item.cents)), 1))
const averageCents = computed(() => visibleMembers.value.length ? Math.round(totalCents.value / visibleMembers.value.length) : 0)
const medianCents = computed(() => calculateMedianCents(visibleMembers.value.map(member => member.cents)))
const stateCount = computed(() => new Set(visibleMembers.value.map(member => member.state).filter(Boolean)).size)
const categoryTotals = computed(() => {
  const totals = new Map<string, number>()
  for (const row of rows.value) totals.set(row.category, (totals.get(row.category) ?? 0) + row.cents)
  return [...totals].map(([name, cents], index) => ({ name, cents, color: categoryColors[index % categoryColors.length],
    share: totalCents.value ? cents / totalCents.value * 100 : 0 })).sort((a, b) => b.cents - a.cents)
})
const rankedMembers = computed(() => [...visibleMembers.value].sort((a, b) => b.cents - a.cents))
const partyRankings = computed(() => {
  const totals = new Map<string, number>()
  for (const row of rows.value) totals.set(row.party, (totals.get(row.party) ?? 0) + row.cents)
  return [...totals].map(([party, cents]) => ({ party, cents })).sort((a, b) => b.cents - a.cents)
})
const rankMaximum = computed(() => Math.max(...rankedMembers.value.map(member => member.cents), 1))
const partyRankMaximum = computed(() => Math.max(...partyRankings.value.map(party => party.cents), 1))
const reversePartyRanking = ref(false)
const showAllParties = ref(false)
const displayedPartyRankings = computed(() => {
  const ordered = reversePartyRanking.value ? [...partyRankings.value].reverse() : partyRankings.value
  return showAllParties.value ? ordered : ordered.slice(0, 10)
})
const reverseRanking = ref(false)
const showMoreMembers = ref(false)
const displayedMembers = computed(() => reverseRanking.value ? [...rankedMembers.value].reverse() : rankedMembers.value)
const memberSliceLimit = computed(() => showMoreMembers.value ? 15 : 5)
const activeFilters = computed(() => filters.status !== 'em-exercicio' || filters.period !== 'ano' || Boolean(filters.state || filters.party || filters.search))
function memberRoute(id: string) {
  return { path: `/gastos/${id.replace(':', '-')}`, query: periodQuery(filters) }
}
function selectChamber(chamber: 'deputados' | 'senadores') {
  filters.chamber = chamber
  filters.party = ''
  filters.state = ''
}
function togglePartyFilter(party: string) {
  filters.party = filters.party === party ? '' : party
}
function formatPercent(value: number) {
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 }).format(value)
}
useSeoMeta({ title: 'Gastos da cota parlamentar | Parlamentares', description: 'Consulte despesas oficiais da cota parlamentar de deputados federais e senadores.' })
</script>

<template>
  <div class="dashboard">
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
          Cota para exercício da atividade parlamentar
        </p>
        <h1 id="page-title">
          Gastos do Congresso,<br class="desktop-break"> em detalhe.
        </h1>
        <p class="intro-copy">
          Explore despesas de deputados e senadores por período, partido, estado ou parlamentar.
        </p>
      </div>
      <aside class="scope-note">
        <UIcon
          name="i-lucide-info"
          aria-hidden="true"
        />
        <p>A cota parlamentar cobre parte das despesas do mandato. Não representa seu custo total.</p>
      </aside>
    </section>

    <section
      class="filters"
      aria-label="Filtros de despesas"
    >
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
          aria-label="Filtrar período"
        >
          <option
            v-for="period in periods"
            :key="period.value"
            :value="period.value"
          >{{ period.label }}</option>
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
        <span>Estado</span>
        <select
          v-model="filters.state"
          aria-label="Filtrar por estado"
        >
          <option value="">Todos</option>
          <option
            v-for="[code, name] in stateOptions"
            :key="code"
            :value="code"
          >{{ name }}</option>
        </select>
      </label>

      <label
        class="filter-field filter-collapsible"
        :class="{ 'is-open': mobileFiltersOpen || secondaryFilterCount > 0 }"
      >
        <span>Partido</span>
        <select
          v-model="filters.party"
          aria-label="Filtrar por partido"
        >
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
        class="clear-filters"
        color="neutral"
        variant="ghost"
        size="sm"
        icon="i-lucide-rotate-ccw"
        @click="resetFilters"
      >
        Limpar
      </UButton>
      <CustomPeriodFields
        v-if="filters.period === 'personalizado'"
        v-model:start="filters.startMonth"
        v-model:end="filters.endMonth"
        :years="years"
      />
    </section>

    <label class="search-field">
      <UIcon
        name="i-lucide-search"
        aria-hidden="true"
      />
      <span class="sr-only">Buscar parlamentar, partido ou estado</span>
      <input
        v-model="filters.search"
        type="search"
        placeholder="Buscar parlamentar, partido ou estado"
        autocomplete="off"
      >
    </label>

    <template v-if="!pending && !error">
      <p
        v-if="coverage"
        class="chart-caption"
      >
        {{ filters.status === 'em-exercicio' ? 'Seleção restrita aos parlamentares em exercício na última coleta.' : 'Seleção inclui perfis históricos.' }} {{ coverage.records.toLocaleString('pt-BR') }} registros de cota coletados nos arquivos anuais desta Casa {{ requestedYears.length > 1 ? `entre ${requestedYears[0]} e ${requestedYears.at(-1)}` : `em ${requestedYears[0]}` }}. {{ coverage.ongoing ? 'Ano em andamento: cobertura parcial.' : 'Lançamentos históricos podem ser corrigidos pela fonte.' }}
      </p>
      <section
        id="resumo"
        class="summary"
        aria-label="Resumo das despesas oficiais"
      >
        <article class="summary-item">
          <h2>Despesas de cota na seleção</h2>
          <p>{{ visibleMembers.length ? formatMoney(totalCents) : '—' }}</p>
          <span>{{ periodLabel }}</span>
        </article>
        <article class="summary-item">
          <h2>Parlamentares</h2>
          <p>{{ visibleMembers.length }}</p>
          <span>com registros no recorte</span>
        </article>
        <article class="summary-item">
          <h2>Estados</h2>
          <p>{{ visibleMembers.length ? stateCount : '—' }}</p>
          <span>com registros publicados</span>
        </article>
        <article class="summary-item">
          <h2>Média por parlamentar</h2>
          <p>{{ visibleMembers.length ? formatMoney(averageCents) : '—' }}</p>
          <span>{{ visibleMembers.length ? `Mediana: ${formatMoney(medianCents)}` : 'no período selecionado' }}</span>
        </article>
      </section>

      <section
        class="analysis-panel"
        aria-label="Análise dos gastos"
      >
        <div class="trend-section">
          <header class="section-heading">
            <div>
              <h2>{{ filters.period === 'historico' ? 'Evolução anual' : 'Evolução mensal' }}</h2>
              <p>{{ periodLabel }}</p>
            </div>
            <span class="section-total">{{ visibleMembers.length ? formatMoney(totalCents) : '—' }}</span>
          </header>

          <div
            v-if="visibleMembers.length"
            class="chart-scroll"
            role="region"
            tabindex="0"
            :aria-label="filters.period === 'historico' ? 'Gráfico anual de despesas; deslize horizontalmente para ver todos os anos' : 'Gráfico mensal de despesas; deslize horizontalmente para ver todos os meses'"
          >
            <ol
              class="monthly-chart"
              :class="{ 'quarter-chart': filters.period.startsWith('q'), 'history-chart': filters.period === 'historico', 'custom-chart': filters.period === 'personalizado' }"
            >
              <li
                v-for="item in trendItems"
                :key="item.key"
                class="chart-item"
                :aria-label="`${item.label}: ${item.count ? formatMoney(item.cents) : 'Sem registros'}`"
              >
                <span
                  class="bar-value"
                  aria-hidden="true"
                >{{ item.count ? formatCompactMoney(item.cents) : '—' }}</span>
                <div
                  class="bar-track"
                  aria-hidden="true"
                >
                  <div
                    class="bar-fill"
                    :style="{ height: `${item.count ? Math.max(Math.abs(item.cents) / maximumTrendTotal * 100, 2) : 0}%` }"
                  />
                </div>
                <span
                  class="month-label"
                  aria-hidden="true"
                >{{ item.label }}</span>
              </li>
            </ol>
          </div>
          <div
            v-else
            class="empty-state"
          >
            <UIcon
              name="i-lucide-search-x"
              aria-hidden="true"
            />
            <h3>Nenhum resultado nesta combinação</h3>
            <p>Experimente trocar a busca ou remover algum filtro.</p>
            <UButton
              color="neutral"
              variant="outline"
              size="sm"
              @click="resetFilters"
            >
              Limpar filtros
            </UButton>
          </div>
          <p class="chart-caption">
            {{ filters.period === 'historico' ? 'Totais por ano calculados a partir das competências publicadas pela Casa. Meses sem registro não comprovam gasto zero; o ano corrente continua recebendo lançamentos.' : 'Competência financeira publicada pela Casa. Meses sem registro não comprovam gasto zero; o ano corrente continua recebendo lançamentos.' }}
          </p>
        </div>

        <aside
          class="category-section"
          aria-labelledby="categories-title"
        >
          <header class="section-heading category-heading">
            <div>
              <h2 id="categories-title">
                Por categoria
              </h2>
              <p>Participação no período</p>
            </div>
          </header>
          <ul
            v-if="visibleMembers.length"
            class="category-list"
          >
            <li
              v-for="category in categoryTotals"
              :key="category.name"
            >
              <div class="category-label">
                <span>{{ category.name }}</span>
                <strong>{{ formatPercent(category.share) }}%</strong>
              </div>
              <div
                class="category-track"
                aria-hidden="true"
              >
                <span
                  class="category-fill"
                  :style="{ width: `${Math.max(0, Math.min(100, category.share))}%`, backgroundColor: category.color }"
                />
              </div>
              <span class="category-value">{{ formatMoney(category.cents) }}</span>
            </li>
          </ul>
          <p
            v-else
            class="category-empty"
          >
            Não há registros publicados para esta combinação.
          </p>
          <p class="category-caption">
            Categorias originais da Casa selecionada, sem conversão para categorias da outra Casa.
          </p>
        </aside>
      </section>

      <section
        id="parlamentares"
        class="ranking-section"
        aria-labelledby="ranking-title"
      >
        <header class="ranking-heading">
          <div>
            <h2 id="ranking-title">
              Gastos por parlamentar
            </h2>
            <p>Valores publicados na mesma Casa e no mesmo período. A ordem não mede qualidade ou eficiência.</p>
          </div>
          <span class="ranking-period">{{ filters.chamber === 'deputados' ? 'Câmara' : 'Senado' }} · {{ periodLabel }}</span>
        </header>

        <div class="rankings-board">
          <section
            class="ranking-card"
            aria-labelledby="party-ranking-title"
          >
            <div class="ranking-card-heading">
              <h3 id="party-ranking-title">
                Partidos
              </h3>
              <div
                class="ranking-switch"
                aria-label="Ordenar partidos"
              >
                <button
                  type="button"
                  :aria-pressed="!reversePartyRanking"
                  @click="reversePartyRanking = false"
                >
                  Mais
                </button>
                <button
                  type="button"
                  :aria-pressed="reversePartyRanking"
                  @click="reversePartyRanking = true"
                >
                  Menos
                </button>
              </div>
            </div>
            <ol
              v-if="partyRankings.length"
              class="compact-ranking-list party-ranking-list"
              aria-label="Partidos com despesas publicadas, ordenados por gasto"
            >
              <li
                v-for="(party, index) in displayedPartyRankings"
                :key="party.party"
                :class="{ 'is-active-filter': filters.party === party.party }"
              >
                <span
                  class="rank-number"
                  aria-hidden="true"
                >{{ String(index + 1).padStart(2, '0') }}</span>
                <button
                  type="button"
                  class="compact-rank-name compact-rank-button"
                  :aria-pressed="filters.party === party.party"
                  :title="filters.party === party.party ? 'Remover filtro deste partido' : `Filtrar painel pelo partido ${party.party}`"
                  @click="togglePartyFilter(party.party)"
                >
                  <strong>{{ party.party }}</strong>
                </button>
                <span
                  class="compact-rank-track"
                  aria-hidden="true"
                ><i :style="{ width: `${Math.max(0, party.cents / partyRankMaximum * 100)}%` }" /></span>
                <strong>{{ formatMoney(party.cents) }}</strong>
              </li>
            </ol>
            <p
              v-else
              class="ranking-empty"
            >
              Sem partidos neste recorte.
            </p>
            <button
              v-if="partyRankings.length > 10"
              type="button"
              class="ranking-expand-btn"
              @click="showAllParties = !showAllParties"
            >
              {{ showAllParties ? 'Mostrar top 10 partidos' : `Ver todos os ${partyRankings.length} partidos` }}
              <UIcon
                :name="showAllParties ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
                aria-hidden="true"
              />
            </button>
          </section>

          <section
            class="ranking-card"
            aria-labelledby="member-ranking-title"
          >
            <div class="ranking-card-heading">
              <h3 id="member-ranking-title">
                Parlamentares
              </h3>
              <div
                class="ranking-switch"
                aria-label="Ordenar parlamentares"
              >
                <button
                  type="button"
                  :aria-pressed="!reverseRanking"
                  @click="reverseRanking = false"
                >
                  Mais
                </button>
                <button
                  type="button"
                  :aria-pressed="reverseRanking"
                  @click="reverseRanking = true"
                >
                  Menos
                </button>
              </div>
            </div>
            <ol
              v-if="displayedMembers.length"
              class="compact-ranking-list"
            >
              <li
                v-for="(member, index) in displayedMembers.slice(0, memberSliceLimit)"
                :key="member.id"
              >
                <span
                  class="rank-number"
                  aria-hidden="true"
                >{{ String(index + 1).padStart(2, '0') }}</span>
                <NuxtLink
                  class="compact-rank-name"
                  :to="memberRoute(member.id)"
                >
                  <strong>{{ member.name }}</strong>
                  <small>{{ member.party }} · {{ member.state }}</small>
                </NuxtLink>
                <span
                  class="compact-rank-track"
                  aria-hidden="true"
                ><i :style="{ width: `${Math.max(0, member.cents / rankMaximum * 100)}%` }" /></span>
                <strong>{{ formatMoney(member.cents) }}</strong>
              </li>
            </ol>
            <p
              v-else
              class="ranking-empty"
            >
              Sem parlamentares neste recorte.
            </p>
            <div class="ranking-card-actions">
              <button
                v-if="displayedMembers.length > 5"
                type="button"
                class="ranking-expand-btn"
                @click="showMoreMembers = !showMoreMembers"
              >
                {{ showMoreMembers ? 'Mostrar top 5' : 'Expandir top 15' }}
                <UIcon
                  :name="showMoreMembers ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
                  aria-hidden="true"
                />
              </button>
              <NuxtLink
                class="text-link"
                :to="{ path: '/gastos', query: periodQuery(filters) }"
              >Ver todos ({{ displayedMembers.length }}) <UIcon
                name="i-lucide-arrow-right"
                aria-hidden="true"
              /></NuxtLink>
              <NuxtLink
                class="text-link"
                :to="{ path: '/gastos', query: { ...periodQuery(filters), visao: 'fornecedores' } }"
              >Maiores fornecedores <UIcon
                name="i-lucide-building-2"
                aria-hidden="true"
              /></NuxtLink>
            </div>
          </section>
        </div>
      </section>

      <section
        class="funds-note"
        aria-labelledby="funds-title"
      >
        <div
          class="funds-mark"
          aria-hidden="true"
        >
          <UIcon name="i-lucide-landmark" />
        </div>
        <div>
          <h2 id="funds-title">
            Recursos de partidos e eleições ficam em outra conta
          </h2>
          <p>O Fundo Partidário e o FEFC aparecem em prestações de contas do TSE. Eles não entram no total individual de gastos parlamentares.</p>
        </div>
        <NuxtLink to="/eleicoes">Consultar eleições e TSE <UIcon
          name="i-lucide-arrow-right"
          aria-hidden="true"
        /></NuxtLink>
      </section>

      <section
        id="metodologia"
        class="methodology-note"
        aria-labelledby="method-title"
      >
        <UIcon
          name="i-lucide-book-open-check"
          aria-hidden="true"
        />
        <div>
          <h2 id="method-title">
            Como ler estes números
          </h2>
          <p>Partidos são atribuídos pelo histórico na data do documento, quando verificável. A filiação mostrada no perfil é a atual. Registros sem atribuição verificável ficam em grupo próprio. Rankings incluem apenas parlamentares com registros no recorte.</p>
        </div>
        <NuxtLink to="/fontes">Ver fontes e metodologia <UIcon
          name="i-lucide-arrow-right"
          aria-hidden="true"
        /></NuxtLink>
      </section>
    </template>
  </div>
</template>
