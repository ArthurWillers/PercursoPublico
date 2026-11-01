import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from pipeline.aggregate.expenses import summarize, summarize_suppliers
from pipeline.collect import publish, verify_output
from pipeline.normalize.common import cents, auxiliary_cents, party_at, in_mandate, supplier_key
from pipeline.sources.camara import normalize, mandate_from_history, affiliations_from_history
from pipeline.sources.senado import normalize as normalize_senado
from pipeline.sources.tse import normalize_election, unavailable_election
from pipeline.validate.integrity import validate, validate_suppliers, validate_election


class IntegrityTests(unittest.TestCase):
    def test_auxiliary_subcent_values_are_not_rounded_or_added_to_totals(self):
        self.assertIsNone(auxiliary_cents('39.8409'))
        self.assertIsNone(auxiliary_cents(''))
        self.assertIsNone(auxiliary_cents('-0.001'))
        self.assertEqual(auxiliary_cents('39.8400'), 3984)
        for value in ('NaN', 'Infinity', True, 0.29, 'invalid', '90071992547410'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                auxiliary_cents(value)
    def test_money_is_exact_signed_and_safe(self):
        self.assertEqual(cents('0.29'), 29)
        self.assertEqual(cents(Decimal('-12.34')), -1234)
        self.assertEqual(cents('1.234,56', brazilian=True), 123456)
        for invalid in ('', None, '0.001', '90071992547409.9100000000000000001', 'NaN', 'Infinity', 0.1, True, '90071992547410'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                cents(invalid)

    def test_historical_party_never_uses_current_party(self):
        affiliations = [{'start': '2023-02-01', 'end': '2025-03-14', 'party': 'A'},
                        {'start': '2025-03-16', 'end': None, 'party': 'B'}]
        self.assertEqual(party_at(affiliations, '2025-03-12', 2025, 3), 'A')
        self.assertEqual(party_at(affiliations, '2025-03-20', 2025, 3), 'B')
        self.assertEqual(party_at(affiliations, None, 2025, 3), 'Sem atribuição verificável')
        self.assertEqual(party_at(affiliations, '2025-03-15', 2025, 3), 'Sem atribuição verificável')

    def test_mandate_does_not_use_legislature_start_for_substitute(self):
        mandate = {'start': '2024-04-15', 'end': '2027-01-31'}
        self.assertFalse(in_mandate(mandate, 2024, 4))
        self.assertTrue(in_mandate(mandate, 2024, 5))
        self.assertFalse(in_mandate(mandate, 2023, 2))

    def test_reconciliation_includes_adjustments_and_zero_groups(self):
        member = {'id': 'camara:1', 'chamber': 'deputados'}
        record = {'id': 'camara:r1', 'memberId': member['id'], 'year': 2025, 'month': 1,
                  'party': 'A', 'category': 'Passagens', 'inMandate': False, 'cents': 100,
                  'sourceUrl': 'https://www.camara.leg.br',
                  'portalUrl': 'https://www.camara.leg.br/cota-parlamentar/sumarizado?nuDeputadoId=1'}
        records = [record, {**record, 'id': 'camara:r2', 'cents': -100}]
        summary = summarize(records)
        self.assertEqual(summary[0]['cents'], 0)
        self.assertEqual(summary[0]['count'], 2)
        validate(records, summary, {member['id']: member})
        with self.assertRaises(ValueError):
            validate(records, [], {member['id']: member})
        with self.assertRaises(ValueError):
            validate(records + [record], summary, {member['id']: member})
        with self.assertRaises(ValueError):
            validate(records, summary, {'senado:1': member})

    def test_camera_document_id_is_not_a_deduplication_key(self):
        row = {'vlrLiquido': '10', 'numAno': '2025', 'numMes': '1', 'ideCadastro': '1', 'nuDeputadoId': '3354',
               'datEmissao': '2025-01-01', 'txtDescricao': 'X', 'numSubCota': '1', 'sgPartido': 'B',
               'txtFornecedor': 'F', 'txtCNPJCPF': '', 'ideDocumento': '123', 'txtNumero': 'N',
               'indTipoDocumento': '0', 'urlDocumento': '', 'vlrDocumento': '10', 'vlrGlosa': '0',
               'vlrRestituicao': '', 'datPagamentoRestituicao': '', 'numParcela': '0', 'numLote': '',
               'numRessarcimento': ''}
        members = {'camara:1': {'affiliations': [], 'mandate': None}}
        records, excluded = normalize([row, row, {**row, 'vlrLiquido': '-2'}], 2025, members, 'https://www.camara.leg.br')
        self.assertEqual(len(set(record['id'] for record in records)), 3)
        self.assertEqual(sum(record['cents'] for record in records), 1800)
        self.assertEqual(excluded['records'], 0)
        precise, _excluded = normalize([{**row, 'vlrDocumento': '39.8409'}], 2025, members, 'https://www.camara.leg.br')
        self.assertIsNone(precise[0]['grossCents'])
        self.assertEqual(precise[0]['grossAmountOriginal'], '39.8409')
        self.assertEqual(precise[0]['cents'], 1000)
        portal = urlsplit(records[0]['portalUrl'])
        self.assertEqual(portal.netloc, 'www.camara.leg.br')
        self.assertEqual(portal.path, '/cota-parlamentar/sumarizado')
        self.assertEqual(parse_qs(portal.query)['nuDeputadoId'], ['3354'])
        self.assertEqual(parse_qs(portal.query)['dataInicio'], ['1/2025'])
        self.assertEqual(parse_qs(portal.query)['numDocumento'], ['N'])
        self.assertNotEqual(supplier_key(None, records[0]['id']), supplier_key(None, records[1]['id']))

    def test_mandate_uses_latest_actual_individual_exercise(self):
        history = [{'idLegislatura': 56, 'dataHora': '2019-04-15T09:00', 'situacao': 'Exercício'},
                   {'idLegislatura': 57, 'dataHora': '2023-05-12T09:00', 'situacao': 'Exercício'},
                   {'idLegislatura': 58, 'dataHora': '2027-02-01T09:00', 'situacao': 'Exercício'},
                   {'idLegislatura': 57, 'dataHora': '2025-02-10T09:00', 'situacao': 'Suplência', 'descricaoStatus': 'Afastamento definitivo'}]
        legislatures = {56: {'dataFim': '2023-01-31'}, 57: {'dataFim': '2027-01-31'}}
        mandate = mandate_from_history(history, legislatures, '2026-10-06')
        self.assertEqual(mandate['start'], '2023-05-12')
        self.assertEqual(mandate['end'], '2025-02-10')
        old = mandate_from_history(history[:1], legislatures, '2026-10-06')
        self.assertEqual(old['start'], '2019-04-15')
        self.assertEqual(old['end'], '2023-01-31')

    def test_history_ignores_dates_outside_legislature_and_same_day_conflicts(self):
        legislatures = {56: {'dataInicio': '2019-02-01', 'dataFim': '2023-01-31'},
                        57: {'dataInicio': '2023-02-01', 'dataFim': '2027-01-31'}}
        history = [{'idLegislatura': 56, 'dataHora': '2023-02-01T00:00', 'siglaPartido': 'OLD'},
                   {'idLegislatura': 57, 'dataHora': '2023-02-01T10:00', 'siglaPartido': 'A'},
                   {'idLegislatura': 57, 'dataHora': '2025-03-15T09:00', 'siglaPartido': 'A'},
                   {'idLegislatura': 57, 'dataHora': '2025-03-15T11:00', 'siglaPartido': 'B'}]
        affiliations = affiliations_from_history(history, legislatures, '2026-10-06')
        self.assertEqual(party_at(affiliations, '2023-02-01', 2023, 2), 'A')
        self.assertEqual(party_at(affiliations, '2025-03-15', 2025, 3), 'Sem atribuição verificável')
        self.assertEqual(party_at(affiliations, '2025-03-16', 2025, 3), 'B')

    def test_senate_preserves_missing_category_signed_money_and_official_id(self):
        row = {'ano': 2025, 'mes': 2, 'codSenador': 1, 'id': 123, 'data': None,
               'valorReembolsado': Decimal('-0.29'), 'tipoDespesa': None, 'fornecedor': 'F',
               'cpfCnpj': '', 'documento': None, 'tipoDocumento': None, 'detalhamento': None}
        members = {'senado:1': {'affiliations': [], 'mandate': None}}
        result = normalize_senado([row], 2025, members, 'https://adm.senado.gov.br')[0]
        self.assertEqual(result['cents'], -29)
        self.assertEqual(result['id'], 'senado:123')
        self.assertIsNone(result['portalUrl'])
        self.assertIsNone(result['categoryOriginal'])
        self.assertEqual(result['category'], 'Categoria não informada pela fonte')

    def test_failed_publication_keeps_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'data'
            output.mkdir()
            (output / 'manifest.json').write_text('{"previous":true}')
            with self.assertRaises(ValueError):
                publish(output, {}, [], {2025: []}, {'schemaVersion': 'broken', 'years': [2025]})
            self.assertEqual(json.loads((output / 'manifest.json').read_text()), {'previous': True})

    def test_streaming_failure_after_first_year_keeps_previous_snapshot(self):
        def batches():
            yield 2008, []
            raise ValueError('Ano seguinte incompleto')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'data'
            output.mkdir()
            (output / 'manifest.json').write_text('{"previous":true}')
            with self.assertRaisesRegex(ValueError, 'Ano seguinte incompleto'):
                publish(output, {}, [], {2008: []}, {'schemaVersion': '1.2.0', 'years': [2008, 2009]}, year_batches=batches())
            self.assertEqual(json.loads((output / 'manifest.json').read_text()), {'previous': True})
            self.assertEqual(list(Path(directory).glob('.financial-data-*')), [])

    def test_streamed_years_reconcile_signed_values_and_reject_duplicate_senate_ids(self):
        members = {'senado:1': {'id': 'senado:1', 'name': 'Fixture de teste', 'chamber': 'senadores', 'mandate': None}}
        row = {'id': 'senado:123', 'memberId': 'senado:1', 'year': 2008, 'month': 1, 'party': 'A',
               'category': 'Passagens', 'inMandate': False, 'cents': 100, 'sourceUrl': 'https://example.gov.br'}
        batches = [(2008, [row]), (2009, [{**row, 'id': 'senado:124', 'year': 2009, 'cents': -100}])]
        summaries = {year: summarize(records) for year, records in batches}
        metadata = {'schemaVersion': '1.2.0', 'years': [2008, 2009], 'coverage': []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'data'
            publish(output, members, [], summaries, metadata, year_batches=iter(batches))
            verify_output(output)
            previous = (output / 'manifest.json').read_bytes()
            duplicates = [(2008, [row]), (2009, [{**row, 'year': 2009, 'cents': -100}])]
            with self.assertRaisesRegex(ValueError, 'duplicado entre anos'):
                publish(output, members, [], summaries, metadata, year_batches=iter(duplicates))
            self.assertEqual((output / 'manifest.json').read_bytes(), previous)

    def test_supplier_aggregation_reconciles_and_keeps_unidentified_separate(self):
        members = {
            'camara:1': {'id': 'camara:1', 'name': 'Dep 1', 'chamber': 'deputados', 'mandate': None},
            'senado:2': {'id': 'senado:2', 'name': 'Sen 2', 'chamber': 'senadores', 'mandate': None}
        }
        records = [
            {'id': 'camara:r1', 'memberId': 'camara:1', 'year': 2025, 'month': 1, 'party': 'A',
             'category': 'Passagens', 'inMandate': True, 'cents': 5000, 'supplier': 'Empresa X',
             'supplierId': '12.345.678/0001-99', 'sourceUrl': 'https://www.camara.leg.br',
             'portalUrl': 'https://www.camara.leg.br/cota-parlamentar/sumarizado?nuDeputadoId=1'},
            {'id': 'camara:r2', 'memberId': 'camara:1', 'year': 2025, 'month': 2, 'party': 'A',
             'category': 'Passagens', 'inMandate': True, 'cents': -1000, 'supplier': 'Empresa X',
             'supplierId': '12345678000199', 'sourceUrl': 'https://www.camara.leg.br',
             'portalUrl': 'https://www.camara.leg.br/cota-parlamentar/sumarizado?nuDeputadoId=1'},
            {'id': 'camara:r3', 'memberId': 'camara:1', 'year': 2025, 'month': 3, 'party': 'A',
             'category': 'Passagens', 'inMandate': True, 'cents': 2500, 'supplier': 'Sem CNPJ',
             'supplierId': '00000000000001', 'sourceUrl': 'https://www.camara.leg.br',
             'portalUrl': 'https://www.camara.leg.br/cota-parlamentar/sumarizado?nuDeputadoId=1'},
            {'id': 'senado:10', 'memberId': 'senado:2', 'year': 2025, 'month': 1, 'party': 'B',
             'category': 'Locomoção', 'inMandate': True, 'cents': 8000, 'supplier': 'Empresa X',
             'supplierId': '12.345.678/0001-99', 'sourceUrl': 'https://adm.senado.gov.br',
             'portalUrl': None}
        ]
        supplier_summary = summarize_suppliers(records, 2025)
        self.assertEqual(len(supplier_summary['rows']), 2)
        self.assertEqual(supplier_summary['rows'][0]['supplierKey'], '12345678000199')
        self.assertEqual(supplier_summary['rows'][0]['memberId'], 'camara:1')
        self.assertEqual(supplier_summary['rows'][0]['cents'], 4000)
        self.assertEqual(supplier_summary['rows'][0]['count'], 2)
        self.assertEqual(supplier_summary['unidentified'], [{'memberId': 'camara:1', 'year': 2025, 'cents': 2500, 'count': 1}])
        validate_suppliers(records, supplier_summary, members, 2025)
        with self.assertRaisesRegex(ValueError, 'não reconcilia'):
            validate_suppliers(records, {**supplier_summary, 'unidentified': []}, members, 2025)
        with self.assertRaisesRegex(ValueError, 'Chave de fornecedor inválida'):
            validate_suppliers(records, {
                'year': 2025,
                'unidentified': [],
                'rows': [{'supplierKey': '00000000000001', 'supplier': 'T', 'supplierId': '1', 'memberId': 'camara:1', 'year': 2025, 'cents': 2500, 'count': 1}]
            }, members, 2025)

    def test_tse_election_normalization_and_reconciliation(self):
        candidates = [
            {'SQ_CANDIDATO': '280001', 'CD_CARGO': '6', 'NM_CANDIDATO': 'CANDIDATA FEDERAL',
             'NM_URNA_CANDIDATO': 'CANDIDATA URNA', 'NR_CANDIDATO': '1234', 'SG_PARTIDO': 'PART',
             'SG_UF': 'SP', 'DS_SIT_TOT_TURNO': 'ELEITO POR QP'},
            {'SQ_CANDIDATO': '280002', 'CD_CARGO': '7', 'NM_CANDIDATO': 'ESTADUAL IGNORADO',
             'NM_URNA_CANDIDATO': 'ESTADUAL', 'NR_CANDIDATO': '12345', 'SG_PARTIDO': 'PART',
             'SG_UF': 'SP', 'DS_SIT_TOT_TURNO': 'ELEITO'}
        ]
        revenues = [
            {'SQ_CANDIDATO': '280001', 'CD_CARGO': '6', 'DS_ORIGEM_RECEITA': 'Recursos de partido político',
             'DS_FONTE_RECEITA': 'Fundo Especial de Financiamento de Campanha', 'VR_RECEITA': '100.000,00'},
            {'SQ_CANDIDATO': '280001', 'CD_CARGO': '6', 'DS_ORIGEM_RECEITA': 'Recursos de partido político',
             'DS_FONTE_RECEITA': 'Fundo Partidário', 'VR_RECEITA': '25.000,50'},
            {'SQ_CANDIDATO': '280001', 'CD_CARGO': '6', 'DS_ORIGEM_RECEITA': 'Recursos de pessoas físicas',
             'DS_FONTE_RECEITA': 'Outros Recursos', 'VR_RECEITA': '5.000,00'},
            {'SQ_CANDIDATO': '280001', 'CD_CARGO': '6', 'DS_ORIGEM_RECEITA': 'Recursos próprios',
             'DS_FONTE_RECEITA': 'Outros Recursos', 'VR_RECEITA': '1.000,00'},
            {'SQ_CANDIDATO': '280002', 'CD_CARGO': '7', 'DS_ORIGEM_RECEITA': 'Recursos próprios',
             'DS_FONTE_RECEITA': 'Outros Recursos', 'VR_RECEITA': '999.999,00'}
        ]
        expenses = [
            {'SQ_CANDIDATO': '280001', 'CD_CARGO': '6', 'DS_ORIGEM_DESPESA': 'Publicidade por materiais impressos',
             'NR_CPF_CNPJ_FORNECEDOR': '12.345.678/0001-99', 'NM_FORNECEDOR': 'GRAFICA X',
             'VR_DESPESA_CONTRATADA': '80.000,00'},
            {'SQ_CANDIDATO': '280001', 'CD_CARGO': '6', 'DS_ORIGEM_DESPESA': 'Despesas com pessoal',
             'NR_CPF_CNPJ_FORNECEDOR': '#NULO#', 'NM_FORNECEDOR': 'DIVERSOS',
             'VR_DESPESA_CONTRATADA': '10.000,00'}
        ]
        urls = {'candidates': 'https://cdn.tse.jus.br/cand.zip', 'accounts': 'https://cdn.tse.jus.br/acc.zip'}
        election = normalize_election(candidates, revenues, expenses, 2022, urls)
        validate_election(election)
        self.assertEqual(len(election['candidates']), 1)
        cand = election['candidates'][0]
        self.assertEqual(cand['id'], 'tse:2022:280001')
        self.assertTrue(cand['elected'])
        self.assertEqual(cand['fefcCents'], 10000000)
        self.assertEqual(cand['partyFundCents'], 2500050)
        self.assertEqual(cand['individualCents'], 500000)
        self.assertEqual(cand['ownResourcesCents'], 100000)
        self.assertEqual(cand['totalRevenueCents'], 13100050)
        self.assertEqual(cand['totalExpenseCents'], 9000000)
        self.assertEqual(election['suppliers']['rows'][0]['supplierKey'], '12345678000199')
        self.assertEqual(election['suppliers']['rows'][0]['cents'], 8000000)
        self.assertEqual(election['suppliers']['unidentified'], {'cents': 1000000, 'count': 1})
        validate_election(unavailable_election(2026, 'Ainda não publicado'))
        with self.assertRaisesRegex(ValueError, 'Fornecedores de campanha não reconciliam'):
            validate_election({**election, 'suppliers': {'unidentified': {'cents': 0, 'count': 0}, 'rows': []}})

    def test_tse_municipal_and_historical_elections_reconcile(self):
        mun_candidates = [
            {'SQ_CANDIDATO': '9001', 'CD_CARGO': '11', 'NM_CANDIDATO': 'PREFEITA ELEITA',
             'NM_URNA_CANDIDATO': 'PREFEITA A', 'NR_CANDIDATO': '15', 'SG_PARTIDO': 'MDB',
             'SG_UF': 'SP', 'SG_UE': '71072', 'NM_UE': 'SÃO PAULO', 'DS_SIT_TOT_TURNO': 'ELEITO'},
            {'SQ_CANDIDATO': '9002', 'CD_CARGO': '13', 'NM_CANDIDATO': 'VEREADORA ELEITA',
             'NM_URNA_CANDIDATO': 'VEREADORA B', 'NR_CANDIDATO': '15000', 'SG_PARTIDO': 'MDB',
             'SG_UF': 'SP', 'SG_UE': '71072', 'NM_UE': 'SÃO PAULO', 'DS_SIT_TOT_TURNO': 'ELEITO POR QP'},
            {'SQ_CANDIDATO': '9003', 'CD_CARGO': '13', 'NM_CANDIDATO': 'VEREADOR SUPLENTE',
             'NM_URNA_CANDIDATO': 'VEREADOR C', 'NR_CANDIDATO': '15001', 'SG_PARTIDO': 'MDB',
             'SG_UF': 'SP', 'SG_UE': '71072', 'NM_UE': 'SÃO PAULO', 'DS_SIT_TOT_TURNO': 'SUPLENTE'}
        ]
        mun_revenues = [
            {'SQ_CANDIDATO': '9001', 'CD_CARGO': '11', 'DS_ORIGEM_RECEITA': 'Recursos de partido político',
             'DS_FONTE_RECEITA': 'Fundo Especial de Financiamento de Campanha', 'VR_RECEITA': '500.000,00'},
            {'SQ_CANDIDATO': '9002', 'CD_CARGO': '13', 'DS_ORIGEM_RECEITA': 'Recursos de partido político',
             'DS_FONTE_RECEITA': 'Fundo Partidário', 'VR_RECEITA': '50.000,00'},
            {'SQ_CANDIDATO': '9003', 'CD_CARGO': '13', 'DS_ORIGEM_RECEITA': 'Recursos próprios',
             'DS_FONTE_RECEITA': 'Outros Recursos', 'VR_RECEITA': '2.000,00'}
        ]
        mun_expenses = [
            {'SQ_CANDIDATO': '9001', 'CD_CARGO': '11', 'DS_ORIGEM_DESPESA': 'Marketing',
             'NR_CPF_CNPJ_FORNECEDOR': '12.345.678/0001-99', 'NM_FORNECEDOR': 'AGENCIA MUNICIPAL',
             'VR_DESPESA_CONTRATADA': '400.000,00'},
            {'SQ_CANDIDATO': '9002', 'CD_CARGO': '13', 'DS_ORIGEM_DESPESA': 'Impressos',
             'NR_CPF_CNPJ_FORNECEDOR': '12.345.678/0001-99', 'NM_FORNECEDOR': 'AGENCIA MUNICIPAL',
             'VR_DESPESA_CONTRATADA': '40.000,00'},
            {'SQ_CANDIDATO': '9003', 'CD_CARGO': '13', 'DS_ORIGEM_DESPESA': 'Impressos',
             'NR_CPF_CNPJ_FORNECEDOR': '12.345.678/0001-99', 'NM_FORNECEDOR': 'AGENCIA MUNICIPAL',
             'VR_DESPESA_CONTRATADA': '1.500,00'}
        ]
        urls = {'candidates': 'https://cdn.tse.jus.br/cand2024.zip', 'accounts': 'https://cdn.tse.jus.br/acc2024.zip'}
        mun_election = normalize_election(mun_candidates, mun_revenues, mun_expenses, 2024, urls, max_vereador_candidates=1)
        validate_election(mun_election)
        self.assertEqual(mun_election['scope'], 'municipal')
        self.assertEqual(len(mun_election['candidates']), 2)
        self.assertEqual(len(mun_election['aggregatedCandidates']), 1)
        self.assertEqual(mun_election['aggregatedCandidates'][0]['candidacyCount'], 1)
        self.assertEqual(mun_election['aggregatedCandidates'][0]['totalRevenueCents'], 200000)
        self.assertEqual(mun_election['candidates'][0]['municipality'], 'SÃO PAULO')
        self.assertEqual(mun_election['candidates'][0]['municipalityCode'], '71072')

        hist_candidates = [
            {'SEQUENCIAL_CANDIDATO': '140001', 'DESCRICAO_CARGO': 'SENADOR', 'NOME_CANDIDATO': 'SENADOR HISTORICO',
             'NOME_URNA_CANDIDATO': 'SENADOR 2014', 'NUMERO_CANDIDATO': '456', 'SIGLA_PARTIDO': 'PSDB',
             'UF': 'MG', 'DESC_SIT_TOT_TURNO': 'ELEITO'}
        ]
        hist_revenues = [
            {'SEQUENCIAL_CANDIDATO': '140001', 'DESCRICAO_CARGO': 'SENADOR',
             'DESC_ORIGEM_RECEITA': 'Recursos de partido político', 'FONTE_RECURSO': 'Fundo Partidário',
             'VALOR_RECEITA': '300000,00'}
        ]
        hist_expenses = [
            {'SEQUENCIAL_CANDIDATO': '140001', 'DESCRICAO_CARGO': 'SENADOR',
             'DESC_TIPO_DESPESA': 'Publicidade por jornais e revistas',
             'CPF_CNPJ_FORNECEDOR': '98765432000188', 'NOME_FORNECEDOR': 'EDITORA MG',
             'VALOR_DESPESA': '250000,00'}
        ]
        hist_election = normalize_election(hist_candidates, hist_revenues, hist_expenses, 2014, urls)
        validate_election(hist_election)
        self.assertEqual(hist_election['scope'], 'geral')
        self.assertEqual(hist_election['candidates'][0]['partyFundCents'], 30000000)
        self.assertEqual(hist_election['suppliers']['rows'][0]['supplierKey'], '98765432000188')



        hist_candidates = [
            {'SEQUENCIAL_CANDIDATO': '140001', 'DESCRICAO_CARGO': 'SENADOR', 'NOME_CANDIDATO': 'SENADOR HISTORICO',
             'NOME_URNA_CANDIDATO': 'SENADOR 2014', 'NUMERO_CANDIDATO': '456', 'SIGLA_PARTIDO': 'PSDB',
             'UF': 'MG', 'DESC_SIT_TOT_TURNO': 'ELEITO'}
        ]
        hist_revenues = [
            {'SEQUENCIAL_CANDIDATO': '140001', 'DESCRICAO_CARGO': 'SENADOR',
             'DESC_ORIGEM_RECEITA': 'Recursos de partido político', 'FONTE_RECURSO': 'Fundo Partidário',
             'VALOR_RECEITA': '300000,00'}
        ]
        hist_expenses = [
            {'SEQUENCIAL_CANDIDATO': '140001', 'DESCRICAO_CARGO': 'SENADOR',
             'DESC_TIPO_DESPESA': 'Publicidade por jornais e revistas',
             'CPF_CNPJ_FORNECEDOR': '98765432000188', 'NOME_FORNECEDOR': 'EDITORA MG',
             'VALOR_DESPESA': '250000,00'}
        ]
        hist_election = normalize_election(hist_candidates, hist_revenues, hist_expenses, 2014, urls)
        validate_election(hist_election)
        self.assertEqual(hist_election['scope'], 'geral')
        self.assertEqual(hist_election['candidates'][0]['partyFundCents'], 30000000)
        self.assertEqual(hist_election['suppliers']['rows'][0]['supplierKey'], '98765432000188')


if __name__ == '__main__':
    unittest.main()
