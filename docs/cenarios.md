# Catálogo de cenários

Gerado a partir de `backend/hrlab/generators/events.py`. Cada cenário escolhe ou prepara um colaborador adequado no time artificial, monta o evento e declara a situação final esperada. A suíte compara o esperado com o obtido.


## Fluxo padrão

| Id | Cenário | O que exercita | Esperado |
| --- | --- | --- | --- |
| `promocao_padrao` | Promoção padrão | Analista júnior elegível promovido a pleno. | Concluído, Concluído com ressalvas |
| `promocao_media_gestao` | Promoção para média gerência | Analista sênior vira coordenador: gratificação de 55%, 8h, celular corporativo e trilha de liderança. | Concluído, Concluído com ressalvas |
| `admissao_padrao` | Admissão padrão | Escriturário admitido com VR, VA, saúde, acessos, ASO e S-2200. | Concluído, Concluído com ressalvas |
| `transferencia_mesma_cidade` | Transferência na mesma cidade | Mudança de agência sem mudança de domicílio. | Concluído, Concluído com ressalvas |
| `transferencia_outra_base_com_anuencia` | Transferência para outra base sindical | SP para MG com anuência: troca de sindicato. | Concluído, Concluído com ressalvas |
| `transferencia_provisoria_cargo_confianca` | Transferência provisória de cargo de confiança | Sem anuência, com adicional de transferência de 25%. | Concluído, Concluído com ressalvas |
| `reversao_cargo_confianca` | Reversão de cargo de confiança | Gerente volta a analista: remove gratificação, volta a 6h, revoga acessos. | Concluído, Concluído com ressalvas |
| `desligamento_sem_justa_causa` | Desligamento sem justa causa | Rescisão, ASO demissional, revogação de acessos, S-2299. | Concluído, Concluído com ressalvas |
| `desligamento_executivo_garden_leave` | Desligamento de executivo | Superintendente entra em garden leave de 90 dias. | Concluído, Concluído com ressalvas |
| `afastamento_doenca` | Afastamento por doença | Acessos reduzidos, VR mantido, S-2230. | Concluído, Concluído com ressalvas |
| `licenca_maternidade` | Licença-maternidade | 180 dias e estabilidade da gestante. | Concluído, Concluído com ressalvas |
| `retorno_de_acidente_de_trabalho` | Retorno de acidente de trabalho | Exame de retorno e estabilidade de 12 meses. | Concluído, Concluído com ressalvas |
| `nascimento_de_filho` | Nascimento de filho | Dependente, licença-paternidade e auxílio-creche. | Concluído, Concluído com ressalvas |
| `bonus_padrao` | Bônus padrão | Verba pontual de bônus. | Concluído, Concluído com ressalvas |
| `merito_com_recalculo_de_gratificacao` | Mérito com recálculo de gratificação | Aumento de 6% recalcula a gratificação de 55%. | Concluído, Concluído com ressalvas |
| `alto_potencial_inclusao` | Inclusão no programa de alto potencial | Vale 12 meses a partir da data oficial: bolsa, mentoria, plataforma de liderança e vencimento agendado. | Concluído, Concluído com ressalvas |
| `alto_potencial_vencimento` | Vencimento do programa de alto potencial | Fim da vigência: a linha retira bolsa, mentoria e acesso. | Concluído, Concluído com ressalvas |
| `alto_potencial_renovacao` | Renovação do programa de alto potencial | Vigência estendida por mais 12 meses; vencimento reagendado. | Concluído, Concluído com ressalvas |
| `alto_potencial_encerramento` | Encerramento antecipado do programa | Saída do programa antes do fim; concessões retiradas e vencimento cancelado. | Concluído, Concluído com ressalvas |
| `conformidade_com_divergencia` | Conformidade com divergência | Colaborador com desvio gerado; o plano remedia. | Concluído, Concluído com ressalvas |

## Exige exceção

| Id | Cenário | O que exercita | Esperado |
| --- | --- | --- | --- |
| `promocao_sem_intersticio` | Promoção sem interstício | Escriturário com 5 meses no cargo; exige exceção do HRBP. | Aguardando aprovação |
| `promocao_processo_disciplinar` | Promoção com processo disciplinar | Processo disciplinar aberto exige exceção de compliance. | Aguardando aprovação |
| `promocao_salto_de_nivel` | Promoção com salto de níveis | Escriturário promovido direto a analista pleno. | Aguardando aprovação |
| `promocao_diretor_sem_comite` | Nomeação de diretor sem comitê | Superintendente a diretor sem aprovação do comitê de remuneração. | Aguardando aprovação |
| `admissao_gerente_acima_da_faixa` | Admissão de gerente acima da faixa | Salário acima da faixa exige HRBP; filho pequeno gera auxílio-creche. | Aguardando aprovação |
| `desligamento_pre_aposentadoria` | Desligamento em pré-aposentadoria | Estabilidade da CCT; exige parecer jurídico. | Aguardando aprovação |
| `desligamento_justa_causa_sem_registro` | Justa causa sem registro de falta | Exige parecer jurídico. | Aguardando aprovação |
| `bonus_acima_do_limite` | Bônus acima de 3 salários | Exige comitê de remuneração. | Aguardando aprovação |
| `merito_acima_do_limite` | Mérito acima do limite | 15% exige comitê. | Aguardando aprovação |
| `alto_potencial_avaliacao_baixa` | Alto potencial com avaliação baixa | Avaliação abaixo da política exige o comitê. | Aguardando aprovação |

## Deve bloquear

| Id | Cenário | O que exercita | Esperado |
| --- | --- | --- | --- |
| `promocao_sem_cpa20` | Promoção a gerente sem CPA-20 | Cargo que distribui investimentos exige CPA-20 (bloqueante). | Não elegível |
| `promocao_com_reducao` | Promoção com redução salarial | Novo salário menor que o atual viola a irredutibilidade. | Não elegível |
| `promocao_colaborador_afastado` | Promoção de colaborador afastado | Colaborador afastado não pode ser promovido. | Não elegível |
| `admissao_abaixo_do_piso` | Admissão abaixo do piso | Salário abaixo do piso da CCT. | Não elegível |
| `admissao_menor_de_idade` | Admissão de menor de 18 anos | Contratação CLT regular de menor de idade. | Não elegível |
| `admissao_cpf_invalido` | Admissão com CPF inválido | CPF com dígitos verificadores inválidos. | Não elegível |
| `admissao_gerente_sem_cpa20` | Admissão de gerente sem CPA-20 | Gerente de relacionamento sem certificação. | Não elegível |
| `transferencia_outra_base_sem_anuencia` | Transferência sem anuência | Mudança de domicílio sem anuência de cargo sem confiança (art. 469). | Não elegível |
| `transferencia_dirigente_sindical` | Transferência de dirigente sindical | Dirigente não pode sair da base (art. 543). | Não elegível |
| `desligamento_gestante` | Desligamento de gestante | Estabilidade da gestante impede a dispensa. | Não elegível |
| `desligamento_membro_cipa` | Desligamento de membro da CIPA | Estabilidade de cipeiro. | Não elegível |
| `bonus_com_medida_restritiva` | Bônus com medida restritiva | Malus de compliance impede bônus. | Não elegível |
| `jornada_8h_sem_cargo_de_confianca` | Jornada de 8h sem confiança | Viola o art. 224 da CLT. | Não elegível |
| `alto_potencial_ja_participa` | Alto potencial para quem já participa | Programa já ativo; o caminho é a renovação. | Não elegível |
| `alto_potencial_vencimento_antecipado` | Vencimento antes do fim da vigência | Evento de vencimento com 6 meses de vigência pela frente. | Não elegível |

## Eventos coletivos

| Id | Cenário | O que exercita | Esperado |
| --- | --- | --- | --- |
| `reajuste_cct_coletivo` | Reajuste coletivo da CCT | Data-base: um caso por colaborador da base SEEB-SP. | Concluído |
| `conformidade_coletiva` | Conformidade coletiva | Varredura de todos os colaboradores contra os contratos. | Concluído |

## Estresse e robustez

| Id | Cenário | O que exercita | Esperado |
| --- | --- | --- | --- |
| `evento_duplicado` | Evento duplicado | Mesmo id enviado duas vezes; o segundo é descartado. | Concluído, Concluído com ressalvas, Duplicado |
| `evento_invalido_sem_cargo_destino` | Evento inválido | Promoção sem cargo de destino. | Rejeitado na entrada |
| `colaborador_inexistente` | Colaborador inexistente | Matrícula que não existe. | Rejeitado na entrada |
| `tipo_de_evento_desconhecido` | Tipo de evento desconhecido | Nenhum contrato de processo atende o evento. | Rejeitado na entrada |
| `data_sem_contrato_vigente` | Data sem contrato vigente | Data efetiva anterior à vigência dos contratos. | Rejeitado na entrada |
| `falha_no_sistema_de_beneficios` | Falha no sistema de benefícios | A operadora falha no meio da execução; a saga compensa. | Falhou e compensado |
| `eventos_concorrentes` | Eventos concorrentes | Mérito, bônus e transferência simultâneos para a mesma pessoa; trava e replanejamento. | Concluído, Concluído com ressalvas, Aguardando aprovação |
