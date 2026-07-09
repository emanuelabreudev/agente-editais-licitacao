# Data Card — Benchmark piloto de editais (PNCP)

Gerado automaticamente em 2026-07-09 por `scripts/gerar_data_card.py`.

## Origem e licença

- **Fonte**: Portal Nacional de Contratações Públicas (PNCP) — APIs públicas de
  consulta (`https://pncp.gov.br/api/consulta/v1`) e de documentos
  (`https://pncp.gov.br/pncp-api/v1`), sem autenticação.
- **Licença**: dados públicos e abertos (Lei de Acesso à Informação — Lei 12.527/2011).
- **Janela de coleta**: publicações de 01/06/2026 a 15/06/2026 (snapshot estático).
- **PII**: os documentos são atos administrativos públicos; não há dados pessoais
  sensíveis nem necessidade de anonimização.

## Composição da amostra

- **Nº de editais**: 16
- **Modalidades**: Concorrência - Eletrônica, Dispensa, Pregão - Eletrônico
- **UFs**: ES, GO, MA, PA, PI, RR, RS, SP
- **Orçamento sigiloso/ausente**: 2 caso(s) (tratados como indisponibilidade, não erro do modelo)

## Ground truth

Os campos-alvo vêm dos **metadados oficiais** da contratação no PNCP
(`dataEncerramentoProposta`, `valorTotalEstimado`, `modalidadeNome`,
`objetoCompra`, `razaoSocial`, `ufSigla`, `criterioJulgamentoNome` dos itens).
O campo `gt_presente_no_texto` em `benchmark.json` indica, por campo, se o valor
oficial é verificável no texto do documento baixado (alguns órgãos publicam no
PNCP apenas documentos resumidos).

## Documentos (rastreabilidade)

PDFs/DOCX brutos ficam em `data/raw/` (fora do versionamento); para reproduzir,
rode `make coletar` e confira os hashes abaixo.

| id_edital | documento | tipo | bytes | método extração | SHA256 |
|---|---|---|---|---|---|
| 88201298000149-1-000679-2026 | Edital-e-anexos-Proc-039.2026---PE-017.2 | Edital | 254302 | docx | `7e1924a4db7a1d72…` |
| 88861448000140-1-000291-2026 | edital_30_OK.pdf | Edital | 265520 | pypdf | `99ead5f989a58f15…` |
| 88243688000181-1-000049-2026 | Anexo-do-Edital---Termo-de-Referencia | Edital | 466174 | pypdf | `c9e9bf837c2ed02b…` |
| 34812644000104-1-000006-2026 | 38924005900012026000 | Edital | 855524 | pypdf | `3deb7b5be041f03d…` |
| 46374500000194-1-004194-2026 | 09018305901542026000 | Edital | 11787436 | pypdf | `7ad36b5a84b5fa61…` |
| 46374500000194-1-004195-2026 | 09018305901672026001 | Edital | 763400 | pypdf | `87d34424c998daf0…` |
| 12122065000199-1-000067-2026 | 187939_editais_1780290509.zip | Edital | 8917800 | pypdf | `48dd318ecc5ee438…` |
| 56024581000156-1-000199-2026 | 98696903900052026000 | Edital | 11524468 | pypdf | `33769879893489e2…` |
| 02304470000174-1-000068-2026 | 92662903900012026000 | Edital | 24029481 | pypdf | `b4d55927614565b1…` |
| 22981427000150-1-000015-2026 | 98059303900032026000 | Edital | 2357326 | pypdf | `54ab4264dec6d947…` |
| 22981427000150-1-000016-2026 | 98059303900042026000 | Edital | 1731657 | pypdf | `41a8f5bd26972c36…` |
| 22981427000150-1-000017-2026 | 98059303900062026000 | Edital | 2911117 | pypdf | `6df5c9335f5e2675…` |
| 02928213000103-1-000033-2026 | Certidão de Publicação 609 | Aviso de Contratação Direta | 156129 | pypdf | `0b29a7328e99faf3…` |
| 02928213000103-1-000034-2026 | Certidão de Publicação 610 | Aviso de Contratação Direta | 156102 | pypdf | `108646dfd41060f5…` |
| 01519467000105-1-000040-2026 | DL_007__Servicos_de_Ornamentacao_edital | Edital | 609938 | pypdf | `6cdb15c5971af986…` |
| 01519467000105-1-000041-2026 | DL_008__Preparacao_Festejos | Edital | 722037 | pypdf | `8e490d3acbdb64c6…` |

Hashes completos em `data/benchmark/documentos.json`.

## Vieses e limitações conhecidos

- Amostra piloto (n=16) concentrada em uma janela de 2 semanas de 2026;
  modalidades de menor volume (inexigibilidade) podem não aparecer.
- Municípios pequenos publicam avisos de dispensa muito curtos (1 página);
  campos oficiais podem não constar no documento (ver `gt_presente_no_texto`).
- PDFs escaneados dependem de OCR (Tesseract); sem os binários instalados as
  páginas de imagem ficam vazias e são reportadas em `extracao_meta.json`.
