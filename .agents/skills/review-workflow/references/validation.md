# Validação e comandos

Leia ao executar o protocolo formal, integrar validação de outra stack ou
registrar um finding/encaminhamento. Os CLIs continuam sendo a interface canônica.

## Contrato de validação

O recorder usa esta precedência:

1. `openspec/handoff.json`: contrato estruturado existente, com comando,
   evidência por gate e verificador nativo. Em revisão comum, substitui apenas o
   caminho da evidência pelo da sessão; não cria uma change.

2. `.review-validation.json` na raiz: comando agregado declarado pelo projeto,
   para projetos sem contrato estruturado. Exemplo:

   ```json
   {"validationCommand": "npm run check"}
   ```

   Também pode declarar `make check` ou `lefthook run pre-push`. O comando deve
   executar toda a validação exigida pelo projeto e retornar sucesso somente
   quando ela terminar com sucesso. O recorder registra um gate bloqueante
   agregado; não inventa resultados individuais ou estágios não observados.

3. `.pre-commit-config.yaml`: executa `pre-commit run --all-files` quando há hooks
   sem estágios explícitos. Hooks por estágio exigem contrato estruturado ou um
   comando agregado declarado que execute todos os estágios exigidos.

O JSON de comando aceita apenas `validationCommand`, uma string não vazia. Os
argumentos são separados como argv, sem shell implícito: para múltiplas etapas,
declare um script ou task do próprio projeto. Não crie nem reduza o contrato
durante uma revisão para conseguir aprovação. Se ele faltar ou não representar
a validação exigida, informe a lacuna e preserve `INCOMPLETE`.

Para CI, o comando local precisa aguardar e conferir os jobs exigidos do commit
revisado. Apenas iniciar o pipeline não constitui validação aprovada.

O recorder rejeita alterações de estado durante a execução. O fechamento confere
comando, contrato, escopo e arquivos registrados e o hash do estado atual. No modo
estruturado, também confere integridade, gates importados e verificador nativo.
O hash detecta mudança; não autentica o revisor nem prova qualidade dos testes.

## Execução e evidência

```bash
python3 .agents/skills/review-workflow/scripts/record-gate-report.py \
  --session-dir .agents/sessions/<review>
```

Acrescente `--change <change-name>` apenas para uma change OpenSpec existente. A
evidência nativa de revisão comum fica em
`.agents/sessions/<review>/evidence/gate-report.json`; o relatório importado da
sessão fica em `artifacts/gate-report.json`. O verificador nativo precisa aceitar
esse caminho. Evidência antiga, comando falho ou verificador incompatível não
podem produzir aprovação.

## Registro de finding

Envie JSON pelo stdin; não escreva o artefato diretamente:

```bash
python3 .agents/skills/review-workflow/scripts/append-finding.py \
  --session-dir .agents/sessions/<review> <<'JSON'
{
  "topic": "behavior:runtime",
  "severity": "blocker",
  "confidence": "high",
  "summary": "Short actionable summary.",
  "impact": "Concrete runtime or contract impact.",
  "recommendedAction": "Specific correction required before approval.",
  "evidence": {
    "file": "src/example.py",
    "line": 42,
    "snippet": "minimal relevant snippet"
  }
}
JSON
```

## Encaminhamento de segurança

Crie primeiro o encaminhamento pendente e envie ao `security-engineer`:

```bash
python3 .agents/skills/review-workflow/scripts/create-security-handoff.py \
  --session-dir .agents/sessions/<review> \
  --reason "Review the authorization finding."
```

Após receber e conferir a análise independente, registre o resultado com
`--status cleared`, `changes_required` ou `waived`, conforme a conclusão, mais
`--reviewed-by security-engineer --review-summary "<concrete assessment>"`.
Sem resposta do especialista, preserve o estado pendente. O artefato guarda a
procedência declarada, não uma autenticação de identidade.

## Conclusão dos itens e exportação

Repita o primeiro comando para cada item realmente revisado:

```bash
python3 .agents/skills/review-workflow/scripts/mark-review-item-done.py \
  --session-dir .agents/sessions/<review> --item-id RVI-001
python3 .agents/skills/review-workflow/scripts/consolidate-verdict.py \
  --session-dir .agents/sessions/<review>
python3 .agents/skills/review-workflow/scripts/export-review-summary.py \
  --session-dir .agents/sessions/<review>
```

O resumo deve informar se o escopo foi restrito por caminho ou ao índice staged.
Um parecer sobre esse escopo não aprova mudanças excluídas da revisão.
Em revisão staged, as diferenças visíveis ao Git devem corresponder ao índice em
todo o repositório, inclusive fora de `--path`: alterações unstaged e arquivos
não rastreados não ignorados podem fornecer dependências ausentes do commit.
O fechamento exclui
apenas a própria sessão e a evidência nativa desse controle. Reconcilie essas
diferenças ou use o escopo `worktree`; gates do working tree não comprovam uma
versão diferente do índice.
Em revisão por refs, o checkout deve estar limpo no `headRef`; validação de outro
commit ou com modificações locais não aprova a revisão pedida. Um escopo vazio,
mesmo com arquivos de contexto declarados, não produz aprovação formal.
Os commits resolvidos de base/head ficam no escopo da sessão, plano e gates.
Se uma branch usada como ref avançar, inicie outra sessão, mesmo que os nomes
dos arquivos do diff continuem iguais.

O fingerprint inclui os bits de execução dos arquivos regulares. Uma mudança de
permissão durante ou depois da validação invalida a evidência, mesmo quando os
bytes não mudam. A comparação considera o modo executável mesmo se o projeto
usar `core.filemode=false`, sem alterar essa configuração. Após atualizar esse
controle, execute novamente os gates para
substituir os fingerprints anteriores.
