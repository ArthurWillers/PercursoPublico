<script setup lang="ts">
import type { Manifest } from '~/types/financial'
import { formatMoney, formatCollectionDate } from '~/utils/financial'
import { publicDataUrl } from '~/utils/publicDataUrl'

const baseURL = useRuntimeConfig().app.baseURL
const { data: manifest, error, status, refresh } = useFetch<Manifest>(publicDataUrl('index.json', baseURL), { server: false })

useSeoMeta({
  title: 'Fontes e metodologia',
  description: 'Fontes oficiais, cobertura coletada, regras de atribuição e limites dos dados financeiros publicados.'
})

const sources = [
  {
    eyebrow: 'Câmara dos Deputados',
    title: 'Cota parlamentar (CEAP)',
    detail: 'A Câmara publica despesas de cota desde 2008. O arquivo anual inclui categoria, fornecedor, identificador de CPF/CNPJ, documento fiscal e informações do parlamentar. Alguns registros podem vir sem identificador ou com identificadores técnicos; a origem é preservada.',
    coverage: 'Integrado: arquivos anuais e histórico',
    href: 'https://dadosabertos.camara.leg.br/swagger/api.html',
    link: 'Abrir API e downloads'
  },
  {
    eyebrow: 'Senado Federal',
    title: 'Cota parlamentar (CEAPS)',
    detail: 'A CEAPS está disponível em CSV e serviço web, com atualização diária. É uma fonte separada da CEAP da Câmara; as categorias originais são preservadas, sem comparação direta entre Casas.',
    coverage: 'Integrado: API por ano, com IDs',
    href: 'https://www12.senado.leg.br/dados-abertos/conjuntos?grupo=senadores&portal=Administrativo',
    link: 'Abrir catálogo do Senado'
  },
  {
    eyebrow: 'Senado Federal',
    title: 'Saúde, viagens e outros benefícios',
    detail: 'Há conjuntos específicos para despesas de saúde, passagens fora da cota e outros benefícios. O relatório de saúde consultado não individualiza despesas nem identifica prestadores por proteção à intimidade; a cobertura não permite atribuir esses valores a cada senador.',
    coverage: 'Cobertura varia por benefício',
    href: 'https://www12.senado.leg.br/transparencia/sen/sis/despesas-com-assistencia-a-saude-de-senadores-e-ex-senadores',
    link: 'Ver relatório de saúde'
  },
  {
    eyebrow: 'Câmara dos Deputados',
    title: 'Remuneração e viagens oficiais',
    detail: 'O portal da Câmara oferece consulta à remuneração dos deputados e informações de viagens oficiais, além de cota, moradia e outras verbas. São trilhas distintas; o projeto precisa conferir formato, histórico e individualização de cada conjunto antes de compará-los.',
    coverage: 'Consultas e relatórios',
    href: 'https://www.camara.leg.br/transparencia/gastos-parlamentares/',
    link: 'Abrir gastos parlamentares'
  },
  {
    eyebrow: 'Câmara dos Deputados',
    title: 'Folha remuneratória',
    detail: 'A consulta nominal reúne fichas financeiras pagas pela Câmara, incluindo deputados em exercício e aposentados. Esse valor efetivamente pago deve ficar separado do subsídio previsto em tabela e das despesas reembolsadas.',
    coverage: 'Consulta nominal e relatórios',
    href: 'https://www2.camara.leg.br/transparencia/recursos-humanos/remuneracao',
    link: 'Abrir área de remuneração'
  },
  {
    eyebrow: 'Senado Federal',
    title: 'Subsídio e remuneração',
    detail: 'O portal do Senado publica remuneração/subsídio de senadores ativos e aposentados. Esse valor será mantido separado de cotas e reembolsos, com a periodicidade e o detalhamento informados pela fonte.',
    coverage: 'Dados publicados pelo Senado',
    href: 'https://www12.senado.leg.br/transparencia/prestacao-de-contas/paginas/remuneracao-e-subsidio-recebidos',
    link: 'Ver página de remuneração do Senado'
  },
  {
    eyebrow: 'TSE',
    title: 'Prestação anual dos partidos',
    detail: 'O TSE publica arquivos anuais das prestações de contas partidárias. Os valores descrevem as contas da organização e devem ser exibidos em uma comparação partidária própria, sem serem atribuídos ao parlamentar.',
    coverage: 'Contas partidárias anuais',
    href: 'https://dadosabertos.tse.jus.br/group/prestacao-de-contas-partidarias',
    link: 'Abrir dados abertos do TSE'
  },
  {
    eyebrow: 'TSE',
    title: 'Contas eleitorais, FP e FEFC',
    detail: 'As prestações de contas eleitorais identificam despesas contratadas e receitas de campanha (FEFC, Fundo Partidário, pessoas físicas e recursos próprios) para Eleições Gerais (2010–2026: Deputado Federal e Senador, com suporte a Presidente e Governador conforme a cobertura coletada) e Municipais (2008–2024: Prefeito e Vereador). Ficam em seção própria (/eleicoes), sem soma aos gastos do mandato.',
    coverage: 'Integrado em /eleicoes (2008 a 2026)',
    href: 'https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-eleitorais',
    link: 'Ver arquivos do TSE'
  }
]

const principles = [
  ['Revisão das fontes', 'O ano corrente e o anterior são revalidados a cada atualização quinzenal. Anos antigos e cadastros históricos são revisados após 365 dias, ou antes por revisão manual. Fontes reutilizadas mantêm seu horário original de coleta; o horário do processamento não indica uma nova consulta de todas as fontes.'],
  ['Competência financeira', 'O período usa numAno/numMes da CEAP e ano/mes da CEAPS, não a emissão da nota. O ano corrente é parcial e fontes podem receber lançamentos tardios.'],
  ['Valores e ajustes', 'CEAP usa vlrLiquido; CEAPS usa valorReembolsado. Valores negativos ficam na soma. Valores brutos, restituições e glosas da Câmara são preservados nos JSONs. Frações de centavo em campos auxiliares históricos ficam apenas no texto original, sem arredondamento; a restituição não é subtraída novamente do líquido.'],
  ['Registros repetidos', 'CEAPS usa o ID oficial, sem repetição. Na CEAP, ideDocumento não é único: a identidade usa SHA-256 da linha e número da ocorrência idêntica. Nenhuma linha é removida por ter o mesmo fornecedor, documento ou valor.'],
  ['Partido histórico', 'Atribuímos pelo histórico oficial na emissão do documento. Se falta data, só usamos uma filiação que cubra todo o mês. Eventos da Câmara fora dos limites oficiais da legislatura são ignorados, e a filiação não é extrapolada após seu fim. Dias com partidos conflitantes e lacunas ficam sem atribuição verificável. O partido anual do CSV é preservado, mas não usado para inferir filiações passadas.'],
  ['Mandato individual', 'O início vem do primeiro exercício individual registrado no mandato mais recente. Meses completos de competência dentro dos limites são somados; meses de fronteira incompletos ficam de fora. Mandatos iniciados antes da cobertura coletada ou em andamento têm cobertura parcial.'],
  ['Lideranças da Câmara', 'Linhas CEAP sem ideCadastro, como lideranças, não entram em perfis individuais nem rankings. Quantidade e valor excluídos estão na tabela de cobertura e no manifesto.'],
  ['Outros recursos do Senado', 'Totais por tipo vêm de recursos-utilizados, com o código parlamentar na URL. São anuais, não são rateados por trimestre, mandato ou período personalizado nem somados à cota. HTTP 404 indica indisponibilidade para aquele cadastro, nunca zero.'],
  ['Remuneração e saúde', 'Folhas sem vínculo validado por identificador parlamentar não são atribuídas por nome ou estimadas pelo subsídio tabelado. Despesas de saúde não individualizadas permanecem fora dos perfis.'],
  ['Identidade estável', 'Junções por identificador da Casa, nunca apenas pelo nome. Filiação partidária deve respeitar a data da despesa.'],
  ['Período com cobertura', '“Mandato” usa as datas daquele mandato e só soma registros disponíveis. Uma coleta parcial aparece como parcial, nunca como total.'],
  ['Sem registro não é zero', 'Dado ausente, não individualizado ou coleta incompleta terá estado próprio, sem ser convertido em gasto zero.'],
  ['Origem preservada', 'A categoria e o identificador originais ficam disponíveis. Agregados devem reconciliar com as despesas publicadas.'],
  ['Pessoas e históricos eleitorais', 'A busca por pessoa reúne registros ligados exclusivamente por CPF oficial com dígitos verificadores (TSE e Câmara). Nomes servem apenas à busca. CPF ausente ou conflitante mantém registros separados; o cadastro do Senado ainda não tem ligação eleitoral verificável. O histórico cobre somente as candidaturas individuais já processadas, com limitação de vereadores. Cada eleição e cada mandato mantêm valores próprios.'],
  ['Contas eleitorais separadas do mandato', 'Candidaturas de eleições gerais (Presidente, Governador, Deputado Federal e Senador) e municipais (Prefeito e Vereador) usam o identificador tse:{ano}:{sq_candidato} e aparecem em /eleicoes. Receitas de FEFC, Fundo Partidário e doações não são somadas às cotas parlamentares, e o cruzamento entre fornecedores de campanha e fornecedores de cota usa exclusivamente CPF/CNPJ de 11 ou 14 dígitos.'],
  ['Consulta cadastral auxiliar', 'Se houver CNPJ/CPF publicado, uma consulta cadastral opcional poderá acrescentar contexto. Ela não modifica a despesa nem substitui a fonte oficial.']
]
</script>

<template>
  <main class="sources-page">
    <p class="breadcrumbs">
      <NuxtLink to="/">Visão geral</NuxtLink><span aria-hidden="true">/</span> Fontes e metodologia
    </p>

    <header class="sources-intro">
      <p class="intro-kicker">
        Transparência também é mostrar limites
      </p>
      <h1>De onde vem cada número.</h1>
      <p>As despesas de cotas vêm dos arquivos anuais CEAP da Câmara e da API CEAPS do Senado. Perfis, fotos e históricos são oficiais. Recursos fora da cota do Senado aparecem em totais anuais separados, e as contas eleitorais do TSE ficam isoladas em seção própria. Remuneração, outros benefícios da Câmara e contas partidárias anuais ainda não estão integrados.</p>
      <span class="integration-status"><i aria-hidden="true" /> Cotas e eleições integradas · demais conjuntos com cobertura própria</span>
    </header>

    <DataStatus
      :pending="status === 'pending' || status === 'idle'"
      :failed="Boolean(error)"
      :manifest="manifest"
      @retry="refresh"
    />
    <section
      v-if="manifest"
      class="suppliers-panel"
      aria-labelledby="coverage-title"
    >
      <header class="profile-panel-heading">
        <div>
          <h2 id="coverage-title">
            Cobertura desta publicação
          </h2><p>Schema {{ manifest.schemaVersion }} · processado {{ formatCollectionDate(manifest.generatedAt) }}. “Coletado” significa leitura completa da fonte disponível, não garantia de que todos os gastos já foram lançados pela Casa.</p>
        </div>
      </header><div class="supplier-table-wrap">
        <table class="supplier-table">
          <thead>
            <tr>
              <th scope="col">
                Casa / ano
              </th><th scope="col">
                Registros individuais
              </th><th scope="col">
                Valor individual
              </th><th scope="col">
                Último mês com registro
              </th><th scope="col">
                Fonte consultada em
              </th><th scope="col">
                Sem parlamentar identificável
              </th><th scope="col">
                Situação
              </th>
            </tr>
          </thead><tbody>
            <tr
              v-for="item in manifest.coverage"
              :key="`${item.chamber}:${item.year}`"
            >
              <td data-label="Casa / ano">
                <a
                  :href="item.sourceUrl"
                  target="_blank"
                  rel="noreferrer"
                >{{ item.chamber === 'deputados' ? 'Câmara' : 'Senado' }} / {{ item.year }}</a>
              </td>
              <td data-label="Registros individuais">
                {{ item.records.toLocaleString('pt-BR') }}
              </td>
              <td data-label="Valor individual">
                {{ formatMoney(item.cents) }}
              </td>
              <td data-label="Último mês">
                {{ item.latestMonth ? `${item.latestMonth}/${item.year}` : 'Sem registros' }}
              </td>
              <td data-label="Fonte consultada em">
                {{ item.fetchedAt ? formatCollectionDate(item.fetchedAt) : 'Ver manifesto' }}
              </td>
              <td data-label="Sem parlamentar">
                {{ item.unattributed.records }} registros · {{ formatMoney(item.unattributed.cents) }}
              </td>
              <td data-label="Situação">
                {{ item.ongoing ? 'Ano parcial' : 'Ano encerrado, sujeito a correções' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div><p class="supplier-footnote">
        O <a
          :href="publicDataUrl('manifest.json', baseURL)"
          target="_blank"
          rel="noreferrer"
        >manifesto completo</a> publica URLs, horários de coleta ISO 8601 com fuso e checksums de cada arquivo. Os JSONs são gerados e validados antes da publicação.
      </p>
    </section>
    <section
      class="source-cards"
      aria-label="Fontes públicas"
    >
      <article
        v-for="source in sources"
        :key="source.title"
        class="source-card"
      >
        <header>
          <span>{{ source.eyebrow }}</span><UIcon
            name="i-lucide-arrow-up-right"
            aria-hidden="true"
          />
        </header>
        <h2>{{ source.title }}</h2>
        <p>{{ source.detail }}</p>
        <footer>
          <span>{{ source.coverage }}</span><a
            :href="source.href"
            target="_blank"
            rel="noreferrer"
          >{{ source.link }} <UIcon
            name="i-lucide-external-link"
            aria-hidden="true"
          /></a>
        </footer>
      </article>
    </section>

    <section
      class="methodology-section"
      aria-labelledby="methodology-title"
    >
      <div class="methodology-title-block">
        <span
          class="methodology-icon"
          aria-hidden="true"
        ><UIcon name="i-lucide-scale" /></span>
        <div>
          <p class="intro-kicker">
            Regras de leitura
          </p><h2 id="methodology-title">
            Como tratamos os dados
          </h2>
        </div>
      </div>
      <dl class="principle-list">
        <div
          v-for="[title, description] in principles"
          :key="title"
        >
          <dt>{{ title }}</dt><dd>{{ description }}</dd>
        </div>
      </dl>
    </section>

    <section class="profile-image-note">
      <div
        class="disclosure-icon"
        aria-hidden="true"
      >
        <UIcon name="i-lucide-image" />
      </div>
      <div>
        <h2>Fotos dos parlamentares</h2>
        <p>Os serviços da Câmara e do Senado incluem URLs de foto para parlamentares. Os perfis usam a URL oficial fornecida pela Casa, com iniciais como alternativa quando a imagem não estiver disponível.</p>
        <div class="source-photo-links">
          <a
            href="https://www2.camara.leg.br/transparencia/dados-abertos/dados-abertos-legislativo/webservices/deputados/obterdeputados"
            target="_blank"
            rel="noreferrer"
          >Fotos da Câmara <UIcon
            name="i-lucide-external-link"
            aria-hidden="true"
          /></a>
          <a
            href="https://www12.senado.leg.br/dados-abertos/legislativo/parlamentares/senadores-em-exercicio/info/webservice-de-senadores-em-exercicio"
            target="_blank"
            rel="noreferrer"
          >Fotos e mandatos do Senado <UIcon
            name="i-lucide-external-link"
            aria-hidden="true"
          /></a>
        </div>
      </div>
    </section>

    <footer class="sources-footer">
      <p>Dados oficiais são publicados por cada instituição. Este site é independente e não representa a Câmara, o Senado ou o TSE.</p>
      <NuxtLink to="/">Voltar à visão geral <UIcon
        name="i-lucide-arrow-right"
        aria-hidden="true"
      /></NuxtLink>
    </footer>
  </main>
</template>
