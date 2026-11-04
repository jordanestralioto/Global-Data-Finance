# Review Rubric

Rubrica independente de projeto para calibrar findings, confidence e bloqueios
do protocolo `review-workflow`.

## Checklist IDs

- `SEC-TRUST`
- `SEC-AUTHZ`
- `SEC-SECRETS`
- `IFACE-CONTRACT`
- `IFACE-COMPAT`
- `DATA-CONTRACT`
- `DATA-QUERY`
- `DATA-OWNERSHIP`
- `BEHAVIOR-CORRECTNESS`
- `BEHAVIOR-STATE`
- `TEST-COVERAGE`
- `TEST-REGRESSION`
- `DOCS-CONTRACT`
- `DOCS-TRACEABILITY`

## Severity

- `blocker`: quebra comportamento, contrato, gate bloqueante, dado ou fronteira
  de confianca.
- `warning`: risco material, regressao plausivel ou cobertura insuficiente em
  caminho importante.
- `nit`: melhoria opcional de consistencia, legibilidade ou cleanup local.

## Confidence

- `high`: evidencia direta no diff, artifact ou gate deterministico.
- `medium`: sinal forte com pequena dependencia de contexto adjacente.
- `low`: suspeita plausivel que ainda depende de confirmacao adicional.

## Blocking Policy

- `blocker` com `high` ou `medium` bloqueia o verdict.
- `warning` nao bloqueia sozinho, mas aparece no resumo final.
- `nit` nunca bloqueia e serve apenas como orientacao.
