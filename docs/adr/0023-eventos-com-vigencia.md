# 0023. Eventos com vigência e relógio simulado

## Contexto

Fernando pediu um mecanismo para eventos que têm vigência, com o exemplo do programa de alto potencial, que vale por um ano a partir da data oficial. Até aqui todo evento produzia efeito uma vez, na data efetiva, e nada voltava a acontecer sozinho. Um programa com prazo precisa de três coisas que a linha não tinha:

- lembrar quando ele termina;
- emitir um evento quando a data chegar, sem ninguém disparar à mão;
- desfazer o que o programa concedeu, com a mesma elegibilidade, auditoria e conferência de qualquer outra mudança.

Esperar um ano para ver o vencimento não serve para testar nem para demonstrar.

## Decisão

- **O programa fica no cadastro.** O colaborador ganha a lista `programas`. Cada item tem código, nome, data oficial de início, fim, status (`ATIVO`, `EXPIRADO`, `ENCERRADO`), dias de aviso, o que concede (verbas, benefícios e acessos), os eventos de aviso e de vencimento, as renovações e o caso de origem.
- **A duração vem de contrato.** A política (`politica.programas.ALTO_POTENCIAL`) define:
  - duração em meses (12) e dias de aviso (30);
  - avaliação mínima e tempo de casa mínimo;
  - limite de renovações;
  - o que o programa concede: bolsa de desenvolvimento, mentoria executiva e acesso à plataforma de liderança;
  - os eventos de aviso e de vencimento.

  O processo `PROC_PROGRAMA_ALTO_POTENCIAL` calcula `fim = somar_meses(data_oficial, duracao_meses)` e grava esse fim no programa. Mudar a duração na política vale para as próximas inclusões; quem já está no programa mantém o fim registrado.
- **As concessões fazem parte do estado alvo.** Enquanto o programa está `ATIVO`, as concessões entram no estado alvo, ao lado do que o cargo e a norma exigem.
  - Na inclusão, o plano deriva a bolsa, a mentoria e o acesso pela diferença com o estado alvo.
  - Quando o programa vence ou é encerrado, as concessões saem do estado alvo e o plano deriva a retirada.
  - Outros processos (promoção, conformidade) não retiram nada enquanto o programa está ativo.
  - A situação do vínculo continua valendo por cima: afastamento e desligamento reduzem acessos como antes.
- **Quatro operações novas na prateleira (sistema DESENVOLVIMENTO):** `INCLUIR_PROGRAMA`, `RENOVAR_PROGRAMA`, `REGISTRAR_AVISO_PROGRAMA` e `ENCERRAR_PROGRAMA`. Todas são compensáveis pela saga, como as demais.
- **Cinco processos:** inclusão, aviso de vencimento, vencimento, renovação e encerramento antecipado. O desligamento também encerra os programas ativos. Os eventos de aviso e de vencimento passam pela linha inteira, e as regras impedem os erros previsíveis:
  - vencimento antes do fim;
  - aviso de uma vigência que já foi renovada;
  - nova inclusão de quem já participa;
  - data oficial no futuro.
- **A agenda é derivada, não guardada.** `vigencia.py` lê os programas ativos e calcula os itens da agenda:
  - o aviso, em `fim - aviso_dias`, se ainda não foi enviado;
  - o vencimento, em `fim`.

  Renovar muda o fim e por isso reagenda os dois. Encerrar antes do fim tira o programa de `ATIVO` e por isso cancela os dois. Não existe fila de agendamentos para manter em sincronia com o cadastro.
- **Cada item da agenda é emitido uma única vez.**
  - O id do evento é fixo: colaborador, programa, fim e tipo.
  - Antes de enviar, o item é reservado com `HSETNX` em `hr:vigencia:emitidos`, o que basta com vários workers, a API e o gerador de cenários ao mesmo tempo.
  - O aviso é pulado quando a data já passou do fim, porque o vencimento cobre o caso.
- **Relógio simulado.** A data de negócio fica em `hr:clock`; sem valor, é o calendário real. A tela Vigências (e a API) avança dias ou vai para uma data. Mudar o relógio confere a agenda na hora, e cada worker também confere a cada `AGENDA_INTERVAL_S` segundos (padrão 5). A data simulada passa a valer para:
  - eventos sem data efetiva;
  - cenários gerados;
  - a conformidade da tela Colaboradores;
  - o perfil.

  Cada mudança do relógio vai para o log (`RELOGIO`), e cada evento emitido pela agenda também (`AGENDA_VIGENCIA`).

## Alternativas consideradas

- **Fila de agendamentos (sorted set por data).** É o desenho clássico, mas exige cancelar e reagendar em toda renovação, encerramento ou desligamento, e qualquer esquecimento deixa um vencimento órfão. Derivar a agenda do cadastro elimina essa classe de erro, ao custo de varrer os colaboradores a cada conferência (barato no tamanho do laboratório).
- **Retirar as concessões por operações explícitas no processo de vencimento.** Funcionaria para o vencimento, mas uma promoção ou uma conferência de conformidade no meio do ano retiraria a bolsa e o acesso, porque eles não estariam no estado alvo de ninguém.
- **Usar a data real com prazos curtos (minutos).** Distorce o domínio, que fala em meses, e não testa as datas de calendário (fim de mês, ano bissexto).

## Consequências

- Avançar o relógio afeta todas as contas de tempo do laboratório (tempo de casa, tempo no cargo, estabilidades), como aconteceria na vida real. Para voltar, use "Voltar ao calendário real".
- O cenário de vencimento da suíte prepara um programa que termina hoje e reserva o id do vencimento antes de preparar o colaborador, para que a agenda não emita o mesmo evento em paralelo. Os outros cenários deixam a agenda real, então avançar o relógio depois da suíte vence também os programas que eles prepararam.
- Se um caso de vencimento terminar sem efeito (não elegível, por exemplo), o item continua reservado e não é reemitido. O caminho é reprocessar o caso ou enviar o evento à mão.
- Reiniciar o laboratório limpa as reservas da agenda junto com os casos.
- Um programa novo (por exemplo, sucessão ou mentoria reversa) é só uma entrada em `politica.programas` e um processo de inclusão. Aviso, vencimento, renovação e encerramento são genéricos e recebem o código do programa em `dados.programa`.
