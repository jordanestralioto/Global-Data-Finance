---
name: review-workflow
description: >-
  Use para revisar diffs, changes e PRs, com leitura leve ou parecer estruturado. Ative quando a
  solicitação envolver "abrir sessão de revisão", "montar plano por risco",
  "registrar apontamento", "gerar parecer", "fechar revisão", "ler gate-report",
  "preparar encaminhamento de segurança", "rodar revisão isolada", "review de
  PR", "review rápido", "revisa esse diff" ou "segunda leitura", ou revisar uma mudança antes de
  encerrá-la. Não use para validação mecânica isolada de comandos; prefira
  `lint-and-validate`. Não use para auditoria de segurança no terminal;
  encaminhe para `security-engineer`.
---

# Review Workflow

## Profundidade

Use leitura leve para alteração pequena e local de texto ou apresentação, sem
mudança em contratos, segurança, dados, dependências, CI ou validação. Leia o diff
e contexto, relate achados acionáveis e informe o que foi validado. Dispense os
artefatos e não emita `APPROVED` formal nesse modo. Tamanho sozinho não prova
baixo risco; uma mudança curta de autorização ou de asserção exige mais contexto.

Use o protocolo completo quando houver risco material, OpenSpec, necessidade de
rastreabilidade ou pedido de aprovação/parecer formal. O script calcula o parecer
pelos artefatos e gates; não prova que toda falha foi encontrada nem autentica o
revisor. Revisão isolada é um controle separado.

## Procedimento

1. Leia `AGENTS.md`, o estado de Git, o diff e contexto suficiente para delimitar
   a revisão. Escolha `worktree` (staged, unstaged e não rastreados), `staged` ou
   refs. Use `--path` para restringir a arquivos ou subárvores; informe esse limite
   no resultado. A sessão deriva os arquivos do Git e o fechamento confere o mesmo
   escopo. `--changed-file` acrescenta contexto, sem ocultar arquivos desse escopo.
2. Crie a sessão ou retome com `--resume --session-dir <sessão>`. Não recrie uma
   sessão existente. Se o plano estiver em `draft`, gere-o após a leitura inicial
   do diff. Os packs sugeridos por caminhos são pistas; use `--risk` para incluir
   riscos encontrados no conteúdo. Cada arquivo deve aparecer em um item.
3. Revise cada item com a seção `Como revisar` e avalie `Revisão isolada`.
   Registre apenas achados acionáveis com `scripts/append-finding.py`.
   Expanda contexto adjacente com `scripts/expand-review-item-context.py` quando
   faltar evidência; não salve suspeita como fato.
4. Execute `scripts/record-gate-report.py` com o contrato declarado pelo projeto.
   Leia [validação e comandos](references/validation.md) para formatos, exemplos
   de findings e encaminhamento. Inspecione entrypoints locais antes de executar.
   Use `--change` somente para uma change OpenSpec existente; evidência de revisão
   comum fica na sessão. Não crie uma change apenas para armazenar relatório.
5. Encaminhe findings materiais de segurança, conclua os itens com
   `scripts/mark-review-item-done.py`, consolide com
   `scripts/consolidate-verdict.py` e exporte com
   `scripts/export-review-summary.py`. Se os arquivos do escopo mudaram depois do
   planejamento concluído, abra uma nova sessão; se só o conteúdo mudou, revise
   novamente o item afetado antes de reexecutar a validação.

```bash
python3 .agents/skills/review-workflow/scripts/init-review-session.py \
  --change-type bug-fix --changed-by codex --scope worktree --path src
python3 .agents/skills/review-workflow/scripts/build-review-plan.py \
  --session-dir .agents/sessions/<review> --risk interface
python3 .agents/skills/review-workflow/scripts/record-gate-report.py \
  --session-dir .agents/sessions/<review>
```

Para PR, informe `--base-ref <base> --head-ref <head>`; o escopo `refs` é inferido.
O diff usa `base...head`. Sem refs, o padrão é `worktree`. Caminhos são relativos
à raiz do repositório e `--path` pode ser repetido. Sessões anteriores sem escopo
explícito são conferidas por refs, quando presentes, ou pelo working tree inteiro.
Para refs, execute a validação em checkout limpo no `headRef`, usando outro
worktree quando necessário. Arquivos de contexto sem mudanças Git não bastam
para aprovação formal.
Para staged, reconcilie alterações unstaged e arquivos não rastreados de todo o
repositório antes de fechar: dependências fora do diff também afetam os gates.
Sessões por refs fixam os commits da base e do head no plano e nos gates; refs
movidas ou sessões antigas sem esses commits exigem uma nova sessão.

## Como revisar

Classifique por risco: `security` para limites de confiança; `interface` para
contratos e entradas/saídas; `data` para integridade e persistência; `behavior`
para runtime; `tests` para regressão/evidência; `docs` para contratos escritos.
Nomes de arquivos não substituem a leitura. `scripts/detect-security-touch.py`
compartilha as pistas do planejador e pode ajudar na triagem; não determina se
uma vulnerabilidade existe ou se a revisão está completa.

- Compare objetivo e diff: identifique mudanças fora do escopo, chamadas afetadas,
  dependências e contratos. Confira que imports, pacotes e APIs novos existem na
  versão/configuração do projeto; não aceite dependência presumida pelo agente.
- Procure um caso concreto que quebre: limites, entradas inválidas, transições de
  estado, falha externa, ownership e compatibilidade com consumidores adjacentes.
  Abra código suficiente para demonstrar impacto, sem transformar toda revisão
  em auditoria geral.
- Leia mudanças nos testes: asserção removida, expectativa relaxada, teste
  desativado ou mock que substitui justamente o comportamento alterado pode
  esconder regressão. Verifique se o teste falharia com o defeito original.
- Confira evidência e integração: arquivo importado novo deve estar incluído no
  commit; sucesso de lint não demonstra semântica; gates antigos não validam o
  estado atual. Considere exclusões e caminhos não rastreados.
- Para cada achado, registre arquivo/linha, evidência mínima, impacto e ação
  concreta. Separe `blocker`, `warning` e `nit`, com confiança `high`, `medium` ou
  `low`. Descarte opinião de estilo coberta por ferramenta e candidato sem prova.

## Revisão isolada

Use um agente neutro ou contexto limpo quando a mesma IA implementou e revisa,
houver pedido de segunda leitura, ou a mudança tocar risco material/comportamento
central. A ausência dessa capacidade não bloqueia a revisão principal; informe a
limitação. Dispense-a em mudança trivial ou validação apenas mecânica.

Envie somente objetivo, arquivos e escopo, sessão, plano e gates disponíveis.
Peça leitura sem edições ou alterações de artefatos, sem parecer final, retornando
apenas candidatos com item relacionado, severidade, confiança, arquivo/linha,
evidência, impacto e ação. Valide cada candidato antes de registrá-lo. Se não
houver problema material, aceite "sem apontamentos materiais".

Não use `developer-engineer` como revisor neutro padrão. Se só esse papel estiver
disponível, dispense a etapa e declare a limitação. Reserve `security-engineer`
para encaminhamento de risco material de segurança.

## Segurança e fechamento

Todo finding `security:` não descartado, com severidade `blocker` ou `warning` e
confiança `high` ou `medium`, exige `scripts/create-security-handoff.py` e análise
do `security-engineer`, mesmo sem pack de segurança no plano. Só registre
`cleared` ou `waived` após conferir a resposta independente, com
`--reviewed-by security-engineer` e `--review-summary`. O CLI registra a declaração,
sem autenticar a identidade do especialista.

Gere os artefatos canônicos pelos scripts, sem editar JSON manualmente. O parecer
preserva `CHANGES_REQUIRED` para gate bloqueante falho e `SECURITY_REVIEW_REQUIRED`
para segurança pendente. Evidência ausente/incompatível, arquivo omitido ou estado
alterado exige `INCOMPLETE`. Execute novamente a validação depois de mudanças;
o hash vincula a evidência ao estado, sem assinatura ou garantia de cobertura
semântica. Não substitua o contrato por um comando conveniente escolhido na hora.

Informe parecer, achados/bloqueios, escopo e arquivos revisados, gates executados,
segurança, revisão isolada e limitações. Declare quando a mesma IA implementou e
revisou. Exporte o resumo após consolidar o parecer.

## Exemplos

### Caso positivo

**Entrada:** "fecha a revisão desse diff e gera o parecer depois da validação"
**Saída esperada:** derivar escopo de Git, planejar por risco, revisar, executar o
contrato declarado, consolidar e exportar. Para uma leitura pequena de copy sem
parecer formal, entregar a revisão leve sem artefatos.

### Caso negativo

**Entrada:** "só roda os testes e me diz se passou"
**Por quê não:** validação mecânica isolada pertence a `lint-and-validate`.

## Evals de trigger

Deve acionar: "review rápido desse diff", "fecha a revisão com parecer", "faz uma
segunda leitura". Não deve acionar: "só roda os gates", "corrige esse bug" ou
"explora esse possível IDOR". Casos completos e assertions verificáveis ficam em
[references/evals.md](references/evals.md); leia ao avaliar ou alterar o workflow.
