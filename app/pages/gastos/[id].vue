<script setup lang="ts">
import { categoryColors, formatMoney, formatCompactMoney, formatDate, formatPercentage, formatSupplierIdentifier, months } from '~/utils/financial'
import { officialMemberProfileUrl } from '~/utils/member'
import type { Expense } from '~/types/financial'

const route = useRoute()
const { manifest, years, filters, member, pending, error, retry, expenses, periodLabel, totalCents, chamberBenchmark } = useParliamentarianData()
const officialProfileUrl = computed(() => member.value ? officialMemberProfileUrl(member.value) : null)

const categories = computed(() => {
  const totals = new Map<string, number>()
  for (const expense of expenses.value) totals.set(expense.category, (totals.get(expense.category) ?? 0) + expense.cents)
  return [...totals].map(([name, cents], index) => ({
    name,
    cents,
    color: categoryColors[index % categoryColors.length],
    share: totalCents.value ? Number((cents / totalCents.value * 100).toFixed(1)) : 0
  })).sort((a, b) => b.cents - a.cents)
})

const monthlyAmounts = computed(() => {
  if (filters.period === 'historico') {
    return years.value.map((year) => {
      const yearExpenses = expenses.value.filter(expense => expense.year === year)
      return { month: String(year), cents: yearExpenses.reduce((sum, expense) => sum + expense.cents, 0), count: yearExpenses.length }
    })
  }
  const totals = new Map<string, { cents: number, count: number }>()
  for (const expense of expenses.value) {
    const key = `${expense.year}-${String(expense.month).padStart(2, '0')}`
    const item = totals.get(key) ?? { cents: 0, count: 0 }
    item.cents += expense.cents
    item.count++
    totals.set(key, item)
  }
  return [...totals].sort(([a], [b]) => a.localeCompare(b)).map(([month, item]) => ({ month, ...item }))
})

const monthlyMaximum = computed(() => Math.max(...monthlyAmounts.value.map(row => Math.abs(row.cents)), 1))

const totalDisallowedCents = computed(() =>
  expenses.value.reduce((sum, row) => sum + (row.disallowedCents && row.disallowedCents > 0 ? row.disallowedCents : 0), 0)
)

const suppliers = computed(() => {
  const groups = new Map<string, { name: string, identifier: string | null, cents: number, count: number, monthly: Map<string, number> }>()
  for (const expense of expenses.value) {
    const digits = (expense.supplierId ?? '').replace(/\D/g, '')
    const key = [11, 14].includes(digits.length) && Number(digits) > 7 ? digits : `record:${expense.id}`
    const item = groups.get(key) ?? {
      name: expense.supplier || 'Fornecedor não informado',
      identifier: expense.supplierId,
      cents: 0,
      count: 0,
      monthly: new Map<string, number>()
    }
    const month = `${expense.year}-${String(expense.month).padStart(2, '0')}`
    item.cents += expense.cents
    item.count++
    item.monthly.set(month, (item.monthly.get(month) ?? 0) + expense.cents)
    groups.set(key, item)
  }
  return [...groups].map(([key, item]) => {
    const peak = [...item.monthly].sort((a, b) => b[1] - a[1])[0]
    return {
      key,
      ...item,
      share: totalCents.value ? Number((item.cents / totalCents.value * 100).toFixed(1)) : 0,
      averageMonthlyCents: Math.round(item.cents / Math.max(item.monthly.size, 1)),
      peakMonthlyCents: peak?.[1] ?? 0,
      peakMonth: peak?.[0] ?? ''
    }
  }).sort((a, b) => b.cents - a.cents)
})

const otherResources = computed(() => filters.period === 'historico'
  ? member.value?.otherResources ?? []
  : filters.period === 'ano' ? member.value?.otherResources?.filter(resource => resource.year === filters.year) ?? [] : [])

const unavailableResourceYears = computed(() => member.value?.otherResourcesCoverage
  ?.filter(row => row.status === 'unavailable' && (filters.period === 'historico' || row.year === filters.year))
  .map(row => row.year) ?? [])

const categoryFilter = ref(typeof route.query.categoria === 'string' ? route.query.categoria : '')
const supplierFilter = ref(typeof route.query.fornecedor === 'string' ? route.query.fornecedor : '')
const monthFilter = ref('')
const expenseSort = ref<'recentes' | 'antigas' | 'maior' | 'menor'>('recentes')
const showAllSuppliers = ref(false)
const page = ref(1)
const pageSize = 30

watch(() => route.query.fornecedor, (value) => {
  if (typeof value === 'string') supplierFilter.value = value
})

function expenseDateKey(expense: Expense) {
  return expense.issuedAt ?? `${expense.year}-${String(expense.month).padStart(2, '0')}-01`
}

function expenseMonthKey(expense: Expense) {
  return filters.period === 'historico'
    ? String(expense.year)
    : `${expense.year}-${String(expense.month).padStart(2, '0')}`
}

const filteredExpenses = computed(() => {
  const query = supplierFilter.value.trim().toLocaleLowerCase('pt-BR')
  const queryDigits = query.replace(/\D/g, '')
  return expenses.value
    .filter((row) => {
      if (categoryFilter.value && row.category !== categoryFilter.value) return false
      if (monthFilter.value && expenseMonthKey(row) !== monthFilter.value) return false
      if (query) {
        const textMatch = `${row.supplier} ${row.supplierId ?? ''} ${row.description ?? ''}`.toLocaleLowerCase('pt-BR').includes(query)
        const rowDigits = (row.supplierId ?? '').replace(/\D/g, '')
        const digitMatch = queryDigits.length >= 3 && rowDigits.includes(queryDigits)
        if (!textMatch && !digitMatch) return false
      }
      return true
    })
    .sort((a, b) => {
      if (expenseSort.value === 'maior') return b.cents - a.cents || expenseDateKey(b).localeCompare(expenseDateKey(a))
      if (expenseSort.value === 'menor') return a.cents - b.cents || expenseDateKey(b).localeCompare(expenseDateKey(a))
      if (expenseSort.value === 'antigas') return expenseDateKey(a).localeCompare(expenseDateKey(b)) || a.id.localeCompare(b.id)
      return expenseDateKey(b).localeCompare(expenseDateKey(a)) || b.id.localeCompare(a.id)
    })
})

const filteredSubtotalCents = computed(() => filteredExpenses.value.reduce((sum, item) => sum + item.cents, 0))
const hasTableFilters = computed(() => Boolean(categoryFilter.value || supplierFilter.value || monthFilter.value))
const visibleExpenses = computed(() => filteredExpenses.value.slice((page.value - 1) * pageSize, page.value * pageSize))

watch([expenses, categoryFilter, supplierFilter, monthFilter, expenseSort], () => {
  page.value = 1
})

function toggleCategoryFilter(name: string) {
  categoryFilter.value = categoryFilter.value === name ? '' : name
}

function toggleMonthFilter(month: string) {
  monthFilter.value = monthFilter.value === month ? '' : month
}

function filterBySupplier(supplier: { name: string, identifier: string | null, key: string }) {
  const target = !supplier.key.startsWith('record:') ? supplier.key : supplier.name
  supplierFilter.value = supplierFilter.value === target ? '' : target
  const element = document.getElementById('expenses-section')
  element?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function clearTableFilters() {
  categoryFilter.value = ''
  supplierFilter.value = ''
  monthFilter.value = ''
}

function exportExpensesCsv() {
  if (!filteredExpenses.value.length || !member.value) return
  const headers = [
    'Competencia',
    'DataEmissao',
    'Fornecedor',
    'CpfCnpj',
    'Categoria',
    'Detalhamento',
    'PartidoNaData',
    'ValorLiquidoBRL',
    'ValorBrutoBRL',
    'ValorGlosaBRL',
    'Documento',
    'FonteUrl'
  ]
  const escapeCsv = (val: string | number | null | undefined) => {
    const str = String(val ?? '').replace(/"/g, '""')
    return `"${str}"`
  }
  const lines = filteredExpenses.value.map(row => [
    `${String(row.month).padStart(2, '0')}/${row.year}`,
    row.issuedAt ?? '',
    row.supplier ?? '',
    row.supplierId ?? '',
    row.category,
    row.description ?? '',
    row.party,
    (row.cents / 100).toFixed(2),
    row.grossCents !== null && row.grossCents !== undefined ? (row.grossCents / 100).toFixed(2) : (row.grossAmountOriginal ?? ''),
    row.disallowedCents !== null && row.disallowedCents !== undefined ? (row.disallowedCents / 100).toFixed(2) : (row.disallowedAmountOriginal ?? ''),
    row.documentNumber ?? '',
    row.documentUrl || row.portalUrl || row.sourceUrl
  ].map(escapeCsv).join(';'))

  const csvContent = `\uFEFF${headers.join(';')}\n${lines.join('\n')}`
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `despesas-${member.value.id.replace(':', '-')}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

function monthLabel(value: string) {
  if (/^\d{4}$/.test(value)) return value
  return `${months[Number(value.slice(5)) - 1]} ${value.slice(0, 4)}`
}

useSeoMeta({
  title: () => member.value ? `${member.value.name} | Parlamentares` : 'Parlamentar | Parlamentares',
  description: () => member.value ? `Despesas oficiais da cota parlamentar de ${member.value.name}.` : 'Consulta individual de despesas parlamentares.'
})
</script>

<template>
  <div
    v-if="member"
    class="profile-page"
  >
    <p class="breadcrumbs">
      <NuxtLink to="/">Visão geral</NuxtLink>
      <span aria-hidden="true">/</span>
      <NuxtLink to="/gastos">Parlamentares</NuxtLink>
      <span aria-hidden="true">/</span>
      <span>{{ member.name }}</span>
    </p>

    <DataStatus
      :pending="pending"
      :failed="Boolean(error)"
      :manifest="manifest"
      @retry="retry"
    />

    <header class="profile-header">
      <MemberAvatar
        class="profile-avatar"
        :name="member.name"
        :photo-url="member.photoUrl"
      />
      <div class="profile-identity">
        <p class="profile-kicker">
          {{ member.chamber === 'deputados' ? 'Câmara dos Deputados' : 'Senado Federal' }} · {{ member.state }}
          <span class="profile-status-pill">{{ member.current ? 'Em exercício' : 'Histórico / Suplência' }}</span>
        </p>
        <h1>{{ member.name }}</h1>
        <p>{{ member.current ? 'Filiação atual:' : 'Filiação no cadastro:' }} <strong>{{ member.party }}</strong> <span aria-hidden="true">·</span> {{ member.state }}</p>
        <p class="profile-links">
          <a
            v-if="officialProfileUrl"
            :href="officialProfileUrl"
            target="_blank"
            rel="noopener noreferrer"
          >Perfil oficial {{ member.chamber === 'deputados' ? 'na Câmara' : 'no Senado' }}</a>
          <a
            v-if="member.sourceUrl !== officialProfileUrl"
            :href="member.sourceUrl"
            target="_blank"
            rel="noopener noreferrer"
          >Fonte de cadastro</a>
        </p>
      </div>
      <div class="profile-period">
        <label
          v-if="filters.period !== 'historico' && filters.period !== 'personalizado'"
          class="filter-field"
        >
          <span>Ano</span>
          <select
            v-model="filters.year"
            :disabled="filters.period === 'mandato'"
          >
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
            aria-label="Período das despesas"
          >
            <option value="ano">Ano inteiro</option>
            <option value="historico">Histórico disponível</option>
            <option value="personalizado">Período personalizado</option>
            <option
              value="mandato"
              :disabled="!member.mandate"
            >Mandato individual</option>
            <option value="q1">1º trimestre</option>
            <option value="q2">2º trimestre</option>
            <option value="q3">3º trimestre</option>
            <option value="q4">4º trimestre</option>
          </select>
        </label>
      </div>
    </header>

    <section
      v-if="member.affiliations?.length || member.mandate"
      class="profile-history-strip"
      aria-label="Histórico de mandato e filiação partidária"
    >
      <div
        v-if="member.mandate"
        class="profile-history-item"
      >
        <span class="profile-history-label">Mandato registrado:</span>
        <span>{{ formatDate(member.mandate.start) }} a {{ formatDate(member.mandate.end) }}{{ member.mandate.partial ? ' (cobertura parcial)' : '' }}</span>
      </div>
      <div
        v-if="member.affiliations?.length"
        class="profile-history-item"
      >
        <span class="profile-history-label">Histórico partidário oficial:</span>
        <ul class="affiliation-chips">
          <li
            v-for="(item, idx) in member.affiliations"
            :key="`${item.party}-${item.start}-${idx}`"
          >
            <strong>{{ item.party }}</strong>
            <small>{{ formatDate(item.start) }} – {{ item.end ? formatDate(item.end) : 'atual' }}</small>
          </li>
        </ul>
      </div>
    </section>

    <CustomPeriodFields
      v-if="filters.period === 'personalizado'"
      v-model:start="filters.startMonth"
      v-model:end="filters.endMonth"
      :years="years"
    />

    <p
      v-if="filters.period === 'mandato'"
      class="mandate-warning"
    >
      Mandato individual: {{ formatDate(member.mandate?.start) }} a {{ formatDate(member.mandate?.end) }}. Cobertura coletada: {{ years[0] }} a {{ years.at(-1) }}. Meses de fronteira incompletos são excluídos; o mandato em andamento ou iniciado antes da coleta tem cobertura parcial.
    </p>

    <template v-if="!pending && !error">
      <section
        class="profile-total"
        aria-label="Resumo da cota parlamentar"
      >
        <div class="profile-total-main">
          <span>Despesas líquidas publicadas da cota</span>
          <strong>{{ totalCents === null ? 'Sem registros no recorte' : formatMoney(totalCents) }}</strong>
          <small>
            {{ periodLabel }} · {{ expenses.length.toLocaleString('pt-BR') }} {{ expenses.length === 1 ? 'registro' : 'registros' }}
            <template v-if="totalDisallowedCents > 0">
              · {{ formatMoney(totalDisallowedCents) }} em glosas (valores descontados pela Casa)
            </template>
          </small>
        </div>

        <div
          v-if="chamberBenchmark"
          class="profile-benchmarks"
          aria-label="Comparativo na mesma Casa e período"
        >
          <div v-if="chamberBenchmark.rank">
            <span>Posição no período</span>
            <strong>{{ chamberBenchmark.rank }}º <small>de {{ chamberBenchmark.memberCount }}</small></strong>
          </div>
          <div>
            <span>Média da Casa</span>
            <strong>{{ formatMoney(chamberBenchmark.averageCents) }}</strong>
          </div>
          <div>
            <span>Mediana da Casa</span>
            <strong>{{ formatMoney(chamberBenchmark.medianCents) }}</strong>
          </div>
        </div>

        <p>A Cota para o Exercício da Atividade Parlamentar cobre itens definidos por cada Casa e não representa todo o custo do mandato. Comparativos consideram apenas valores publicados na mesma Casa e período.</p>
      </section>

      <section class="profile-content-grid">
        <article
          class="profile-panel"
          aria-labelledby="profile-categories-title"
        >
          <header class="profile-panel-heading">
            <div>
              <h2 id="profile-categories-title">
                Em que gastou
              </h2>
              <p>Clique em uma categoria para filtrar as notas abaixo</p>
            </div>
            <span>{{ periodLabel }}</span>
          </header>
          <ul
            v-if="categories.length"
            class="profile-category-list"
          >
            <li
              v-for="category in categories"
              :key="category.name"
            >
              <button
                type="button"
                class="category-filter-btn"
                :class="{ 'is-selected': categoryFilter === category.name }"
                :aria-pressed="categoryFilter === category.name"
                @click="toggleCategoryFilter(category.name)"
              >
                <div class="category-label">
                  <span>{{ category.name }}</span><strong>{{ formatPercentage(category.share) }}</strong>
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
              </button>
            </li>
          </ul>
          <p
            v-else
            class="category-empty"
          >
            Sem categorias registradas neste período.
          </p>
        </article>

        <article
          class="profile-panel profile-monthly-panel"
          aria-labelledby="profile-monthly-title"
        >
          <header class="profile-panel-heading">
            <div>
              <h2 id="profile-monthly-title">
                Ao longo do tempo
              </h2>
              <p>{{ filters.period === 'historico' ? 'Clique em um ano para filtrar as notas' : 'Clique em um mês para filtrar as notas' }}</p>
            </div>
            <button
              v-if="monthFilter"
              type="button"
              class="chart-clear-btn"
              @click="monthFilter = ''"
            >
              Limpar ({{ monthLabel(monthFilter) }})
            </button>
          </header>
          <ol
            v-if="monthlyAmounts.length"
            class="profile-monthly-chart"
            :class="{ 'quarter-chart': filters.period.startsWith('q') }"
            tabindex="0"
            :aria-label="filters.period === 'historico' ? 'Gráfico de despesas agrupadas por ano; deslize horizontalmente para ver todos os anos' : 'Gráfico de despesas por mês; deslize horizontalmente para ver todos os meses'"
          >
            <li
              v-for="item in monthlyAmounts"
              :key="item.month"
              :class="{ 'is-selected': monthFilter === item.month }"
            >
              <button
                type="button"
                class="profile-month-btn"
                :disabled="!item.count"
                :aria-pressed="monthFilter === item.month"
                :aria-label="`${monthLabel(item.month)}: ${item.count ? formatMoney(item.cents) : 'Sem registros publicados'}`"
                @click="toggleMonthFilter(item.month)"
              >
                <span
                  v-if="item.count"
                  class="profile-month-value"
                  aria-hidden="true"
                  :title="formatMoney(item.cents)"
                >{{ formatCompactMoney(item.cents) }}</span>
                <span
                  v-if="item.count"
                  class="profile-month-bar"
                  aria-hidden="true"
                ><i :style="{ height: `${Math.max(Math.abs(item.cents) / monthlyMaximum * 100, 2)}%` }" /></span>
                <span
                  v-else
                  class="profile-no-records"
                  aria-hidden="true"
                >—</span>
                <span class="profile-month-label">{{ monthLabel(item.month) }}</span>
              </button>
            </li>
          </ol>
          <p
            v-else
            class="category-empty"
          >
            Sem registros publicados no período selecionado.
          </p>
        </article>
      </section>

      <section
        class="suppliers-panel"
        aria-labelledby="suppliers-title"
      >
        <header class="profile-panel-heading">
          <div>
            <h2 id="suppliers-title">
              Fornecedores
            </h2>
            <p>{{ showAllSuppliers ? `Todos os ${suppliers.length} fornecedores` : '15 maiores valores por fornecedor' }}. Total por CPF/CNPJ publicado; identificadores ausentes ficam separados por registro.</p>
          </div>
          <span>Identificação da fonte</span>
        </header>
        <div
          v-if="suppliers.length"
          class="supplier-table-wrap"
        >
          <table class="supplier-table supplier-summary-table">
            <caption class="sr-only">
              Maiores fornecedores no período selecionado, com identificação e valores publicados.
            </caption>
            <colgroup>
              <col>
              <col>
              <col>
              <col>
              <col>
              <col>
            </colgroup>
            <thead>
              <tr>
                <th scope="col">
                  Fornecedor
                </th>
                <th scope="col">
                  CPF/CNPJ
                </th>
                <th scope="col">
                  Participação
                </th>
                <th scope="col">
                  Total no período
                </th>
                <th scope="col">
                  Média nos meses com registros
                </th>
                <th scope="col">
                  Maior mês
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="supplier in (showAllSuppliers ? suppliers : suppliers.slice(0, 15))"
                :key="supplier.key"
              >
                <td data-label="Fornecedor">
                  <strong>{{ supplier.name }}</strong>
                  <div class="supplier-row-actions">
                    <button
                      type="button"
                      class="supplier-filter-link"
                      @click="filterBySupplier(supplier)"
                    >
                      <UIcon
                        name="i-lucide-filter"
                        aria-hidden="true"
                      />
                      <span>Filtrar {{ supplier.count }} {{ supplier.count === 1 ? 'nota' : 'notas' }}</span>
                    </button>
                  </div>
                </td>
                <td data-label="CPF/CNPJ">
                  <span>{{ formatSupplierIdentifier(supplier.identifier) }}</span>
                  <SupplierCnpjLookup :identifier="supplier.identifier" />
                </td>
                <td data-label="Participação">
                  <span>{{ formatPercentage(supplier.share) }}</span>
                </td>
                <td
                  class="supplier-money"
                  data-label="Total no período"
                >
                  <span>{{ formatMoney(supplier.cents) }}</span>
                </td>
                <td
                  class="supplier-money"
                  data-label="Média mensal"
                >
                  <span>{{ formatMoney(supplier.averageMonthlyCents) }}</span>
                </td>
                <td
                  class="supplier-money supplier-peak"
                  data-label="Maior mês"
                >
                  <span>{{ formatMoney(supplier.peakMonthlyCents) }}</span>
                  <small>{{ monthLabel(supplier.peakMonth) }}</small>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div
          v-if="suppliers.length > 15"
          class="supplier-more-wrap"
        >
          <UButton
            color="neutral"
            variant="ghost"
            size="sm"
            :icon="showAllSuppliers ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
            @click="showAllSuppliers = !showAllSuppliers"
          >
            {{ showAllSuppliers ? 'Mostrar apenas os 15 maiores' : `Ver todos os ${suppliers.length} fornecedores do período` }}
          </UButton>
        </div>
        <p class="supplier-footnote">
          Para fornecedores com CNPJ de 14 dígitos, o botão “Consultar CNPJ” busca dados cadastrais públicos em fonte externa sob ação do usuário, sem alterar o registro oficial.
        </p>
      </section>

      <section
        id="expenses-section"
        class="suppliers-panel"
        aria-labelledby="expenses-title"
      >
        <header class="profile-panel-heading">
          <div>
            <h2 id="expenses-title">
              Todas as despesas da cota
            </h2>
            <p>{{ member.chamber === 'deputados' ? 'Cada linha abre a consulta correspondente no portal da Câmara.' : 'Os links apontam para a fonte oficial do Senado.' }} Comprovantes são abertos à parte quando publicados.</p>
          </div>
          <UButton
            v-if="filteredExpenses.length"
            color="neutral"
            variant="outline"
            size="xs"
            icon="i-lucide-download"
            @click="exportExpensesCsv"
          >
            Exportar CSV ({{ filteredExpenses.length }})
          </UButton>
        </header>

        <div class="expense-controls">
          <label class="filter-field">
            <span>Categoria</span>
            <select v-model="categoryFilter">
              <option value="">Todas</option>
              <option
                v-for="category in categories"
                :key="category.name"
                :value="category.name"
              >{{ category.name }}</option>
            </select>
          </label>
          <label class="filter-field">
            <span>Fornecedor, descrição ou CPF/CNPJ</span>
            <input
              v-model="supplierFilter"
              type="search"
              placeholder="Buscar fornecedor, CNPJ ou detalhe"
            >
          </label>
          <label class="filter-field">
            <span>Ordenar notas por</span>
            <select v-model="expenseSort">
              <option value="recentes">Mais recentes</option>
              <option value="antigas">Mais antigas</option>
              <option value="maior">Maior valor</option>
              <option value="menor">Menor valor</option>
            </select>
          </label>
        </div>

        <div
          v-if="hasTableFilters"
          class="active-table-filters"
          role="status"
        >
          <span>
            Filtro ativo: <strong>{{ filteredExpenses.length.toLocaleString('pt-BR') }}</strong> de {{ expenses.length.toLocaleString('pt-BR') }} registros · Subtotal: <strong>{{ formatMoney(filteredSubtotalCents) }}</strong>
          </span>
          <div class="active-filter-chips">
            <button
              v-if="categoryFilter"
              type="button"
              class="filter-chip"
              @click="categoryFilter = ''"
            >
              Categoria: {{ categoryFilter }} ×
            </button>
            <button
              v-if="monthFilter"
              type="button"
              class="filter-chip"
              @click="monthFilter = ''"
            >
              Período: {{ monthLabel(monthFilter) }} ×
            </button>
            <button
              v-if="supplierFilter"
              type="button"
              class="filter-chip"
              @click="supplierFilter = ''"
            >
              Busca: {{ supplierFilter }} ×
            </button>
            <button
              type="button"
              class="filter-chip-clear"
              @click="clearTableFilters"
            >
              Limpar todos
            </button>
          </div>
        </div>

        <div
          class="supplier-table-wrap"
          role="region"
          tabindex="0"
          aria-label="Despesas da cota parlamentar, com competência, fornecedor, categoria, valor e fonte oficial"
        >
          <table class="supplier-table expense-register-table">
            <caption class="sr-only">
              Despesas da cota parlamentar, ordenadas conforme seleção, com competência, fornecedor, categoria, valor e links oficiais.
            </caption>
            <colgroup>
              <col>
              <col>
              <col>
              <col>
              <col>
            </colgroup>
            <thead>
              <tr>
                <th scope="col">
                  Competência
                </th>
                <th scope="col">
                  Fornecedor / CPF ou CNPJ
                </th>
                <th scope="col">
                  Categoria e detalhamento
                </th>
                <th scope="col">
                  Valor líquido
                </th>
                <th scope="col">
                  Fonte oficial
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="expense in visibleExpenses"
                :key="expense.id"
              >
                <td
                  class="expense-period"
                  data-label="Competência"
                >
                  <span>{{ String(expense.month).padStart(2, '0') }}/{{ expense.year }}</span>
                  <small v-if="expense.issuedAt">Emissão: {{ formatDate(expense.issuedAt) }}</small>
                </td>
                <td
                  class="expense-supplier"
                  data-label="Fornecedor"
                >
                  <strong>{{ expense.supplier || 'Não informado' }}</strong>
                  <small>{{ formatSupplierIdentifier(expense.supplierId) }}</small>
                </td>
                <td
                  class="expense-category"
                  data-label="Categoria"
                >
                  <span>{{ expense.category }}</span>
                  <small
                    v-if="expense.description"
                    class="expense-detail-text"
                  >Detalhe: {{ expense.description }}</small>
                  <small>Partido na data: {{ expense.party }}</small>
                </td>
                <td
                  class="expense-amount"
                  data-label="Valor líquido"
                >
                  <span :class="{ 'expense-negative': expense.cents < 0 }">{{ formatMoney(expense.cents) }}</span>
                  <small
                    v-if="expense.cents < 0"
                    class="expense-adjustment-badge"
                  >Estorno / ajuste negativo</small>
                  <small
                    v-if="expense.disallowedCents && expense.disallowedCents > 0"
                    class="expense-glosa-note"
                  >Glosa: {{ formatMoney(expense.disallowedCents) }}{{ expense.grossCents ? ` (Bruto: ${formatMoney(expense.grossCents)})` : '' }}</small>
                  <small
                    v-else-if="expense.disallowedAmountOriginal && expense.disallowedAmountOriginal !== '0'"
                    class="expense-glosa-note"
                  >Glosa original: R$ {{ expense.disallowedAmountOriginal }}</small>
                  <small
                    v-if="expense.restitutionCents && expense.restitutionCents !== 0"
                    class="expense-restitution-note"
                  >Restituição: {{ formatMoney(expense.restitutionCents) }}</small>
                </td>
                <td
                  class="expense-document"
                  data-label="Fonte oficial"
                >
                  <a
                    v-if="expense.portalUrl"
                    class="source-document-link"
                    :href="expense.portalUrl"
                    target="_blank"
                    rel="noreferrer"
                    :aria-label="expense.documentNumber ? `Consultar documento ${expense.documentNumber} no portal da Câmara` : 'Consultar despesas desta competência no portal da Câmara'"
                  >Ver na Câmara</a>
                  <a
                    v-if="expense.documentUrl"
                    class="source-document-link"
                    :href="expense.documentUrl"
                    target="_blank"
                    rel="noreferrer"
                  >Comprovante oficial</a>
                  <a
                    v-if="!expense.portalUrl && !expense.documentUrl"
                    class="source-document-link"
                    :href="expense.sourceUrl"
                    target="_blank"
                    rel="noreferrer"
                  >{{ member.chamber === 'senadores' ? 'Fonte oficial do Senado' : 'Arquivo oficial da Câmara' }}</a>
                  <small>{{ expense.documentNumber ? `Documento ${expense.documentNumber}` : 'Número do documento ausente' }}</small>
                  <small>{{ expense.issuedAt ? formatDate(expense.issuedAt) : 'Data de emissão ausente' }}</small>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p
          v-if="!filteredExpenses.length"
          class="empty-state"
        >
          Nenhuma despesa publicada para esta combinação.
        </p>
        <div class="expense-pagination">
          <UButton
            :disabled="page === 1"
            color="neutral"
            variant="outline"
            @click="page--"
          >
            Anterior
          </UButton>
          <span>{{ filteredExpenses.length.toLocaleString('pt-BR') }} registros · página {{ page }} de {{ Math.max(1, Math.ceil(filteredExpenses.length / pageSize)) }}</span>
          <UButton
            :disabled="page * pageSize >= filteredExpenses.length"
            color="neutral"
            variant="outline"
            @click="page++"
          >
            Próxima
          </UButton>
        </div>
      </section>

      <section
        v-if="otherResources.length"
        class="suppliers-panel"
        aria-labelledby="other-resources-title"
      >
        <header class="profile-panel-heading">
          <div>
            <h2 id="other-resources-title">
              Recursos fora da cota
            </h2>
            <p>{{ filters.period === 'historico' ? `Totais anuais individualizados pelo Senado entre ${years[0]} e ${years.at(-1)}. Não entram no ranking de cotas.` : `Totais anuais individualizados pelo Senado em ${filters.year}. Não entram no ranking de cotas.` }}</p>
          </div>
        </header>
        <dl class="other-resource-list">
          <div
            v-for="resource in otherResources"
            :key="`${resource.year}:${resource.type}`"
          >
            <dt>
              <a
                :href="resource.sourceUrl"
                target="_blank"
                rel="noreferrer"
              >{{ resource.type }}</a>
              <small>{{ resource.year }}</small>
            </dt>
            <dd>{{ formatMoney(resource.cents) }}</dd>
          </div>
        </dl>
        <p
          v-if="unavailableResourceYears.length"
          class="chart-caption"
        >
          A fonte não disponibilizou recursos individualizados para {{ unavailableResourceYears.join(', ') }}. Esses anos não entram no total acima.
        </p>
      </section>
      <p
        v-else-if="member.chamber === 'senadores'"
        class="chart-caption"
      >
        {{ filters.period === 'historico' ? 'A fonte não publicou recursos individualizados para este cadastro no intervalo selecionado.' : 'Recursos fora da cota possuem granularidade anual. Selecione “Ano inteiro” para consultá-los; não é possível rateá-los por trimestre, mandato ou intervalo personalizado.' }}
      </p>

      <section
        class="disclosure-panel"
        aria-labelledby="other-disclosures-title"
      >
        <div
          class="disclosure-icon"
          aria-hidden="true"
        >
          <UIcon name="i-lucide-layers-3" />
        </div>
        <div>
          <h2 id="other-disclosures-title">
            Outros valores públicos, em seções separadas
          </h2>
          <p>Remuneração ainda sem integração por identificador validado. Dados de saúde sem individualização não são atribuídos a pessoas. Outros recursos publicados abaixo permanecem separados da cota.</p>
          <NuxtLink to="/fontes">Ver o que cada fonte publica <UIcon
            name="i-lucide-arrow-right"
            aria-hidden="true"
          /></NuxtLink>
        </div>
        <span class="source-status">{{ member.chamber === 'senadores' && member.otherResourcesCoverage?.some(item => item.year === filters.year && item.status === 'collected') ? 'Recursos anuais integrados' : member.chamber === 'deputados' ? 'Outros recursos não integrados' : 'Recursos anuais indisponíveis' }}</span>
      </section>
    </template>
  </div>

  <div
    v-else
    class="not-found-page"
  >
    <DataStatus
      :pending="pending"
      :failed="Boolean(error)"
      :manifest="manifest"
      @retry="retry"
    />
    <p class="breadcrumbs">
      <NuxtLink to="/">Visão geral</NuxtLink><span aria-hidden="true">/</span> Parlamentar
    </p>
    <UIcon
      name="i-lucide-user-round-search"
      aria-hidden="true"
    />
    <h1>{{ pending ? 'Carregando perfil' : error ? 'Perfil indisponível' : 'Perfil não encontrado' }}</h1>
    <p v-if="!pending && !error">
      Este endereço não corresponde a um perfil disponível nos arquivos publicados.
    </p>
    <UButton
      to="/"
      color="primary"
      icon="i-lucide-arrow-left"
    >
      Voltar à visão geral
    </UButton>
  </div>
</template>
