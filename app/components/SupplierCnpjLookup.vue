<script setup lang="ts">
import { isValidCnpj, formatDate, formatMoney, formatSupplierIdentifier } from '~/utils/financial'

interface CnpjPartner {
  nome_socio?: string
  qualificacao_socio?: string
}

interface CnpjApiResponse {
  cnpj?: string
  razao_social?: string
  nome_fantasia?: string
  descricao_situacao_cadastral?: string
  data_situacao_cadastral?: string
  data_inicio_atividade?: string
  cnae_fiscal_descricao?: string
  natureza_juridica?: string
  porte?: string
  capital_social?: number
  municipio?: string
  uf?: string
  qsa?: CnpjPartner[]
}

const props = defineProps<{
  identifier: string | null | undefined
}>()

const cnpjCache = useState<Record<string, CnpjApiResponse>>('cnpj-enrichment-cache', () => ({}))
const cnpjDigits = computed(() => isValidCnpj(props.identifier))
const trigger = ref<HTMLButtonElement | null>(null)
const open = ref(false)
const loading = ref(false)
const failed = ref(false)
const data = computed(() => (cnpjDigits.value ? cnpjCache.value[cnpjDigits.value] ?? null : null))

async function lookupCnpj() {
  if (!cnpjDigits.value) return
  open.value = true
  if (data.value) return

  loading.value = true
  failed.value = false
  try {
    const response = await fetch(`https://brasilapi.com.br/api/cnpj/v1/${cnpjDigits.value}`, {
      headers: { Accept: 'application/json' }
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const payload = (await response.json()) as CnpjApiResponse
    cnpjCache.value[cnpjDigits.value] = payload
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div
    v-if="cnpjDigits"
    class="cnpj-lookup"
  >
    <button
      ref="trigger"
      type="button"
      class="cnpj-lookup-trigger"
      aria-haspopup="dialog"
      @click="lookupCnpj"
    >
      <UIcon
        name="i-lucide-building-2"
        aria-hidden="true"
      />
      <span>Consultar CNPJ</span>
    </button>

    <UModal
      v-model:open="open"
      title="Cadastro do fornecedor"
      :description="`CNPJ ${formatSupplierIdentifier(cnpjDigits)}`"
      :ui="{ content: 'max-w-2xl', body: 'overflow-y-auto' }"
      @after:leave="trigger?.isConnected && trigger.focus()"
    >
      <template #body>
        <div class="cnpj-modal-content">
          <div class="cnpj-lookup-badge">
            <UIcon
              name="i-lucide-info"
              aria-hidden="true"
            />
            <span>Enriquecimento cadastral de terceiro (BrasilAPI / Receita Federal) · Não altera o dado oficial</span>
          </div>

          <p
            v-if="loading"
            role="status"
            class="cnpj-lookup-status"
          >
            Consultando cadastro externo do CNPJ…
          </p>

          <div
            v-else-if="failed"
            class="cnpj-lookup-error"
            role="status"
          >
            <p>Consulta cadastral externa indisponível para este CNPJ no momento. O registro oficial da despesa permanece inalterado.</p>
            <button
              type="button"
              class="cnpj-lookup-retry"
              @click="lookupCnpj"
            >
              Tentar novamente
            </button>
          </div>

          <dl
            v-else-if="data"
            class="cnpj-lookup-grid"
          >
            <div>
              <dt>Razão social</dt>
              <dd>{{ data.razao_social || 'Não informada' }}</dd>
            </div>
            <div v-if="data.nome_fantasia">
              <dt>Nome fantasia</dt>
              <dd>{{ data.nome_fantasia }}</dd>
            </div>
            <div>
              <dt>Situação cadastral</dt>
              <dd>{{ data.descricao_situacao_cadastral || 'Não informada' }}{{ data.data_situacao_cadastral ? ` (${formatDate(data.data_situacao_cadastral)})` : '' }}</dd>
            </div>
            <div>
              <dt>Início de atividade</dt>
              <dd>{{ formatDate(data.data_inicio_atividade) }}</dd>
            </div>
            <div class="cnpj-lookup-wide">
              <dt>Atividade principal (CNAE)</dt>
              <dd>{{ data.cnae_fiscal_descricao || 'Não informada' }}</dd>
            </div>
            <div v-if="data.municipio || data.uf">
              <dt>Município / UF</dt>
              <dd>{{ [data.municipio, data.uf].filter(Boolean).join(' / ') }}</dd>
            </div>
            <div v-if="typeof data.capital_social === 'number'">
              <dt>Capital social</dt>
              <dd>{{ formatMoney(Math.round(data.capital_social * 100)) }}</dd>
            </div>
            <div
              v-if="data.qsa?.length"
              class="cnpj-lookup-wide"
            >
              <dt>Quadro societário (QSA)</dt>
              <dd>
                <ul class="cnpj-qsa-list">
                  <li
                    v-for="(partner, idx) in data.qsa"
                    :key="idx"
                  >
                    <strong>{{ partner.nome_socio }}</strong>
                    <span v-if="partner.qualificacao_socio"> · {{ partner.qualificacao_socio }}</span>
                  </li>
                </ul>
              </dd>
            </div>
          </dl>
        </div>
      </template>
    </UModal>
  </div>
</template>
