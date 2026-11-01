# Percurso Público

**Pessoas, mandatos e eleições.**

Consulta pública centrada em pessoas, reunindo candidaturas de diferentes eleições e informações financeiras de mandatos de deputados federais e senadores. Interface em português, inteiramente estática, com filtros compartilháveis na URL.

## Implementado

- Consulta por pessoa em `/pessoas`: busca por nomes civis e de urna, filtros por cargo/UF e janela compartilhável por URL com mandatos e candidaturas de diferentes eleições. Cada eleição mantém seus próprios valores; o acesso às despesas do mandato permanece na consulta individual. Cadastro de CNPJ abre em modal, sem expandir células de tabelas.

- Coleta real de todos os registros individuais publicados nos arquivos CEAP da Câmara e na API CEAPS do Senado, de 2008 até o ano corrente por padrão.
- Cadastros atuais e perfis de parlamentares identificados nas despesas do período, inclusive suplentes e ex-parlamentares. O cadastro não se limita aos atuais 513/81 assentos.
- Fotos em URLs oficiais, com alternativa por iniciais; histórico de filiação e limites individuais de mandato quando verificáveis.
- Filtro de situação atual, com “Em exercício” por padrão e “Todos os perfis” para incluir históricos. Usa o cadastro oficial na coleta; escolher um ano de despesas não reconstrói a composição da Casa naquele ano.
- Período personalizado por mês/ano inicial e final, inclusivos, compartilhável na URL e preservado ao abrir um perfil. Permite atravessar anos e filtrar partidos, estados e situação atual.
- Visão geral, rankings por Casa/ano/período e partido histórico, busca individual, índice global de fornecedores por CPF/CNPJ entre parlamentares, categorias originais e despesas paginadas com documento/fonte, glosas e detalhamento.
- Consulta cadastral opcional de CNPJ no navegador sob ação explícita do usuário (via BrasilAPI / Receita Federal), identificada como enriquecimento de terceiro e sem alterar o dado oficial.
- Recursos fora da cota do Senado publicados por código parlamentar em totais anuais separados: diárias, passagens e demais categorias retornadas pela fonte. Não são somados à cota nem rateados por mês, trimestre ou mandato.
- Dados eleitorais do TSE em seção própria (`/eleicoes`) para Eleições Gerais (2010, 2014, 2018, 2022, 2026 — Deputado Federal e Senador; Presidente e Governador conforme a cobertura declarada no arquivo) e Eleições Municipais (2008, 2012, 2016, 2020, 2024 — Prefeito e Vereador, com filtro por município): receitas por origem (FEFC, Fundo Partidário, doações de pessoas físicas, recursos próprios), despesas contratadas, resultado eleitoral, resumo partidário e cruzamento por CPF/CNPJ validado entre fornecedores de campanha e fornecedores da cota parlamentar, mantendo os valores de campanha e mandato estritamente separados.
- Contratos JSON versionados, valores em centavos inteiros, auditoria de fontes/horários/checksums e reconciliação de agregados com detalhes.
- Pipeline Python sem dependências externas; testes offline; GitHub Actions coleta, valida, compacta, gera e publica automaticamente no GitHub Pages duas vezes por mês.

**Ainda não integrado:** remuneração/subsídio, outros recursos da Câmara, assistência à saúde e prestação anual de contas partidárias do TSE. Não foi validada uma ligação por identificador entre folhas remuneratórias e os perfis. Não inferimos pagamentos pelo salário tabelado nem juntamos folhas por nome. Valores ausentes ou não individualizados não são zero.

Não há publicação Cloudflare nem analytics configurados. Proposições, votações e autenticação estão fora do escopo.

A interface oferece navegação com seção ativa, atalhos dentro do perfil individual e visão geral do parlamentar no período. As categorias de campanha têm layout próprio, sem herdar a grade de fornecedores. Links diretos do DivulgaCandContas usam somente pleitos verificados (2022 e 2026); nos demais anos, a interface oferece a busca no portal oficial.

Presidente e governador foram coletados e validados localmente para 2022 e 2026. Para ampliar os arquivos históricos, execute uma nova coleta: o cache eleitoral mudou para `v3-executivo` para não reutilizar pacotes limitados ao Congresso. `collectedOffices` declara os cargos processados, inclusive quando não há registros. Arquivos anteriores continuam legíveis e a interface informa a cobertura pendente desses cargos em vez de exibir zero.

## Desenvolvimento

Use Python 3.12+ e Node.js 24, com o pnpm fixado em `package.json`. Antes de preparar o Nuxt, restaure ou colete os dados para que ele conheça os IDs das rotas estáticas.

```bash
python -m unittest discover -s pipeline/tests -v
python -m pipeline.collect
pnpm install --frozen-lockfile
pnpm dev
```

A leitura dos dados acontece no cliente, com estado de carregamento explícito e sem duplicar os detalhes nos payloads das páginas pré-renderizadas. O site lê somente os arquivos de `public/data/`. Nenhum componente consulta APIs oficiais no navegador. As URLs de fotos/documentos são fornecidas pelas Casas.

```bash
pnpm data:collect                         # revalida anos recentes; reutiliza históricos < 365 dias
python -m pipeline.collect --start-year 2008
python -m pipeline.collect --review-history # força revisão completa antes de 365 dias
python -m pipeline.collect --offline     # reprocessa o cache completo, sem rede
python -m pipeline.collect --resume      # desenvolvimento: cache existente + URLs faltantes
python -m pipeline.refresh_elections --year 2022 --year 2026 # atualiza apenas esses pleitos
pnpm data:test
pnpm data:validate
pnpm check                              # lint, tipos, integridade e generate
```

`pipeline.refresh_elections` reutiliza os arquivos imutáveis do mandato, atualiza os pleitos indicados e seus metadados/checksums em uma pasta temporária e valida toda a publicação antes de substituir o snapshot. Uma falha ou a indisponibilidade de um pleito antes coletado preserva a versão anterior. Aceita `--offline` para reprocessar os novos caches eleitorais sem rede.

`--offline`/`--resume` preservam o horário efetivo de cada resposta no manifesto e identificam a publicação como processada com cache. Não simulam uma nova coleta. Na coleta normal, o ano corrente e o anterior são revalidados a cada execução, com ETag/Last-Modified quando disponíveis. Anos anteriores e cadastros de ex-parlamentares são reutilizados por até 365 dias; depois são revalidados. As respostas reutilizadas preservam `fetchedAt` e têm `cacheReused: true` no manifesto. O `generatedAt` é o horário do processamento, não uma nova consulta de todas as fontes. A política aparece em `collectionPolicy` e cada Casa/ano publica seu próprio horário de coleta. `--review-history` força a revisão dos anos antigos; também está disponível como opção na execução manual dos workflows. Erros transitórios recebem tentativas limitadas; um erro em fonte obrigatória interrompe o processamento.

Na coleta, falhas de conexão, respostas incompletas e HTTP 408, 429, 500, 502, 503 ou 504 recebem até seis tentativas por URL, com esperas de 5, 10, 20, 40 e 60 segundos. Os logs identificam a URL, o erro e a próxima tentativa. Se a fonte continuar indisponível, a coleta falha sem substituir o cache por uma resposta de erro nem publicar dados antigos como uma nova coleta.

`public/data/` e `.cache/pipeline/` ficam fora do Git. Não edite esses arquivos manualmente. Se a coleta/validação falhar, a versão válida local anterior permanece; uma publicação externa só ocorre após sucesso de todo o workflow. Uma execução offline exige cache completo e validado por checksum.

## Arquivos publicados

- `index.json`: cobertura e metadados pequenos para a UI.
- `members.json`: cadastro resumido para listagens.
- `members/{Casa:id}.json`: perfil, histórico e recursos anuais separados quando disponíveis.
- `summary-{ano}.json`: agregados por parlamentar, competência, partido histórico, categoria e elegibilidade ao mandato.
- `suppliers-{ano}.json`: agregados anuais de fornecedores identificados por CPF/CNPJ e parlamentar, reconciliados com os detalhes e mantendo sem identificação separados.
- `elections-{ano}.json`: candidaturas das Eleições Gerais (Presidente, Governador, Deputado Federal e Senador) e Municipais (Prefeito e Vereador) do TSE, receitas por origem (FEFC, Fundo Partidário, pessoas físicas, recursos próprios), despesas contratadas, agregados partidários e fornecedores de campanha.
- `expenses/{Casa:id}/{ano}.json`: detalhes normalizados. Arquivo vazio significa nenhuma linha publicada para esse cadastro/ano na fonte coletada, não comprovação de gasto zero.
- `manifest.json`: versão do schema, cobertura, URLs e horários de coleta ISO 8601 com fuso, checksums de entradas e arquivos publicados e IDs das rotas.

Na pasta publicada pelo GitHub Pages, os resumos, perfis detalhados e arquivos de despesas viram `.json.gz`; a interface os descompacta no navegador. Isso mantém a publicação abaixo do limite de 1 GB. Os checksums do manifesto publicado correspondem aos arquivos compactados.

Contratos em `schemas/`. Os coletores vivem em `pipeline/sources/`, regras exatas em `pipeline/normalize/`, agregação em `pipeline/aggregate/` e invariantes em `pipeline/validate/`. O pipeline primeiro gera uma pasta temporária, valida os arquivos escritos e só então substitui a versão anterior.

## Pessoas e vínculos entre eleições

`people.json` é o índice de busca; `people/{id}.json` traz os registros individuais carregados ao abrir a janela. Contratos em `schemas/people.v1.schema.json` e `schemas/person.v1.schema.json`. A busca usa nomes e aliases, mas a união de registros usa exclusivamente o CPF publicado no cadastro TSE (`consulta_cand`) e no detalhe oficial da Câmara, com verificação dos dígitos. O ID `person:` deriva de SHA-256 com namespace; o CPF usado na junção não é publicado nesses arquivos. Isso não é uma garantia de anonimização.

CPF ausente, mascarado, inválido ou conflitante impede a união; o registro recebe identidade própria de sua fonte. Homônimos permanecem separados. Não há ligação automática entre o cadastro do Senado e as candidaturas: os endpoints integrados do Senado não oferecem CPF compatível. Os nomes nunca são chave de junção. Vínculos sem suporte permanecem explícitos na interface. A cobertura descreve CPFs conflitantes nos cadastros históricos, que não são usados para unir registros. Isso também significa que uma candidatura ausente não comprova que a pessoa não participou daquela eleição. O índice só cobre as candidaturas individuais já publicadas, inclusive a limitação existente de vereadores.

A coleta completa constrói o índice antes de publicar. Para acrescentá-lo a um snapshot existente sem reprocessar as despesas: `python -m pipeline.refresh_elections --people`. A atualização eleitoral reconstrói o índice existente para evitar referências desatualizadas. Falhas preservam a edição anterior. A validação reconcilia todos os cadastros e candidaturas, sem duplicação entre pessoas, e compara os valores de cada candidatura com o arquivo eleitoral de origem.

## Metodologia

A competência usa `numAno/numMes` da CEAP e `ano/mes` da CEAPS. A data de emissão do documento é preservada e usada para a filiação histórica quando disponível; se não houver data, a filiação precisa cobrir o mês inteiro. No histórico da Câmara, eventos com datas fora dos limites oficiais da legislatura são descartados da atribuição temporal; conflitos entre partidos no mesmo dia ficam sem atribuição naquele dia. Lacunas/conflitos ficam em “Sem atribuição verificável”. O partido anual da CEAP é preservado, mas não usado como filiação histórica: a documentação oficial ressalva que ele pode ser o último partido do ano. A filiação ao lado do nome vem do cadastro consultado: atual para parlamentares em exercício e última informada para os demais. Atribuições da Câmara não são extrapoladas além do fim da legislatura verificada.

A CEAP usa `vlrLiquido` e a CEAPS usa `valorReembolsado`, convertidos com `Decimal`. Valores negativos e zeros publicados ficam nos detalhes e agregados. Valor bruto, glosas e restituições da Câmara são preservados como campos auxiliares (inclusive ausências). Alguns arquivos históricos publicam valores auxiliares com frações de centavo: o texto original fica em `grossAmountOriginal`, `disallowedAmountOriginal` e `restitutionAmountOriginal`, com o campo correspondente de centavos como `null` quando não há conversão exata. Esses campos não são arredondados nem usados nos totais; o líquido continua exigindo centavos exatos. Não subtraímos novamente a restituição do líquido. Não há total único de cota, salários e benefícios.

`ideDocumento` da Câmara não identifica uma linha única. Cada ocorrência tem um ID com namespace, ano, SHA-256 do registro original e número da ocorrência idêntica. Não removemos linhas com documento/fornecedor/valor iguais. A CEAPS usa o ID oficial; duplicação desse ID impede publicação. Linhas da Câmara sem `ideCadastro`, como lideranças, ficam fora dos perfis/rankings e seus totais excluídos são publicados na cobertura.

Categorias originais não são convertidas entre Casas. Categorias ausentes no Senado aparecem como “Categoria não informada pela fonte”, preservando `categoryOriginal: null`. CPF/CNPJ ausente, mascarado ou técnico não une fornecedores: esses registros permanecem separados. A média de fornecedor considera apenas meses com registros; o pico identifica competência/ano.

O recorte individual de mandato usa o início do exercício informado pela Casa e o fim disponível daquele mandato, com cobertura parcial quando iniciado antes do primeiro ano coletado, em andamento ou com meses de fronteira incompletos. Como a competência só identifica o mês, meses que não estão inteiramente dentro dos limites ficam de fora. Não há ranking de mandatos individuais com durações diferentes. Rankings usam a mesma Casa, ano, período e fonte; apenas quem possui registros entra na ordenação. Não medem qualidade ou eficiência parlamentar.

Os recursos anuais do Senado usam o código parlamentar na URL oficial. Um HTTP 404 nesse endpoint individual significa indisponibilidade para o cadastro, sem converter em zero; erros transitórios impedem publicação. Saúde não individualizada e remuneração sem vínculo validado ficam fora desses totais. Os dados eleitorais do TSE (`consulta_cand`, `receitas_candidatos` e `despesas_contratadas_candidatos`) aparecem em `/eleicoes` com identificador próprio (`tse:{ano}:{sq_candidato}`), separados dos gastos do mandato; o cruzamento entre fornecedores de campanha e de cota parlamentar usa exclusivamente CPF (11 dígitos) ou CNPJ (14 dígitos) validados, sem juntar pessoas ou empresas por nome. Quando o pacote de uma eleição futura ou histórica não está publicado no CDN do TSE, a cobertura registra a indisponibilidade explícita sem converter em zero.

A página `/fontes` mostra cobertura e regras. “Coletado” confirma leitura integral da fonte disponível, não que a instituição já publicou todos os gastos: o ano corrente é parcial e históricos podem receber correções.

## Verificação e geração estática

```bash
pnpm lint
pnpm typecheck
pnpm generate
```

`generate` verifica a integridade dos JSONs, pré-renderiza as rotas e compacta os arquivos grandes diretamente de `public/data/` para `.output/public`, sem duplicar os JSONs brutos no disco do runner. IDs do manifesto enumeram todas as rotas de perfil; o site em produção não exige backend, Functions ou servidor Nuxt. `pnpm preview` permite conferir o resultado gerado.

O workflow `ci.yml` reprocessa as fontes quando mudam coletores, normalização, agregação, validação ou schemas. Ele restaura primeiro o cache HTTP e aplica a política de revisão anual; não baixa todos os anos novamente. Em mudanças de interface e configuração, restaura um único pacote normalizado, confere checksums e valida antes de gerar e publicar, sem consultar as APIs oficiais. Se o pacote ainda não existe, recupera o snapshot publicado no Pages.

`refresh-data.yml` atualiza os dados nos dias 1 e 15 de cada mês, às 05:30 de Brasília. Revalida sempre o ano corrente e o anterior, e revisa automaticamente cada resposta histórica após 365 dias. Também pode ser executado manualmente pela aba **Actions**, com a opção de forçar a revisão histórica. A primeira coleta de 2008 em diante é mais demorada; os jobs têm limite de 120 minutos para coleta, validação, geração e preservação dos pacotes. O job de deploy tem limite próprio de 10 minutos.

Execuções do ramo `master` ficam em uma fila compartilhada para evitar coletas concorrentes e não cancelar uma coleta longa quando chega uma alteração de interface.

O cache de fontes e o snapshot normalizado são guardados como pacotes `.tar.gz` em pré-lançamentos técnicos `dados-fontes-*` e `dados-site-*` do repositório. São Releases, não commits de dados nem artefatos temporários com expiração. Cada pacote é publicado primeiro como rascunho e só fica disponível para reutilização após completar o upload. Mantemos as duas versões mais recentes de cada tipo. A escrita usa `GITHUB_TOKEN` com `contents: write`, apenas no ramo `master` fora de pull requests; não exige secrets adicionais. Isso evita perder o histórico em cache entre execuções quinzenais e evita a acumulação de artefatos grandes. Os dados são públicos, inclusive os arquivos brutos oficiais desses pacotes.

Anos são normalizados, escritos e validados individualmente para limitar o consumo de memória no runner. IDs de despesas do Senado são conferidos também entre anos. A publicação compactada tem um bloqueio automático antes de atingir 1 GB; ampliar a cobertura no futuro exige medir novamente seu tamanho. Se coleta, validação, geração ou preservação falhar, o job de publicação não roda e a versão válida anterior continua no ar.

Para ativar a publicação, no repositório abra **Settings → Pages → Build and deployment** e selecione **GitHub Actions** como fonte. Depois execute **Actions → Coletar dados e gerar site → Run workflow** para a primeira publicação. Os workflows usam automaticamente o nome atual do repositório como base do site, sem secrets. Renomear o repositório não reconstrói o artefato já publicado; execute o workflow novamente para atualizar os caminhos. O endereço atual é https://arthurwillers.github.io/PercursoPublico/.

## Fontes

- [Câmara — dados abertos](https://dadosabertos.camara.leg.br/swagger/api.html) e [campos da CEAP](https://dadosabertos.camara.leg.br/howtouse/2023-12-26-dados-ceap.html).
- [Senado — catálogo administrativo](https://www12.senado.leg.br/dados-abertos/conjuntos?grupo=senadores&portal=Administrativo) e [API administrativa](https://adm.senado.gov.br/adm-dadosabertos/swagger-ui/index.html).
- [Senado — cadastros, filiações e mandatos](https://legis.senado.leg.br/dadosabertos/docs/).
- [TSE — Repositório de Dados Eleitorais e DivulgaCandContas](https://dadosabertos.tse.jus.br/).

Leia [AGENTS.md](./AGENTS.md) antes de alterar o projeto. Licença MIT, com atribuição preservada do template Nuxt UI.
