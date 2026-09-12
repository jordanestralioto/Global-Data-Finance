# reference.md

## O que esta referencia faz

Esta referencia nao e mais o manual completo do harness.
Ela existe para ajudar a IA e humanos a decidir rapidamente quando usar a skill `lint-and-validate`, o que fazer primeiro e por que esse caminho e o certo.

O guia amplo do runtime fica nas diretrizes de verificacao do repositorio.

## Quando usar esta skill

Use `lint-and-validate` quando o trabalho principal for validacao objetiva de um artefato alterado:

- escolher o comando canonico de verificacao sem inventar fluxo local;
- validar diff comum com gates repo-native e `gate-report`;
- validar uma skill contra `skill-governance`;
- validar agents, manifests e o protocolo `review-workflow`.

## Por que usar esta skill

Ela existe para evitar tres erros comuns:

- escolher gates manualmente por intuicao;
- misturar falha de ambiente com falha de codigo;
- encerrar uma entrega sem evidencias reutilizaveis para `review-workflow` ou security.

Em vez disso, a skill separa o problema por entrypoint canonico:

- Comando oficial declarado pelo projeto consumidor (ou `pre-commit run --all-files`) para diff comum e gates do repo;
- `harness-validate --request <caminho>` para governança e integridade de skills, agents e workflows projetados no consumidor.

## O que fazer na pratica

1. Confirme se o pedido e de validacao, nao de implementacao ou arquitetura.
2. Escolha o entrypoint pelo artefato:
   - diff comum e gates: comando oficial do projeto ou `pre-commit run --all-files`
   - skills, agents e workflows projetados: `harness-validate --request <caminho>` (ex.: `harness-validate --request .agents/validation/request.json`)
3. Execute o comando e confira o exit code e o status de cada gate.
4. Responda com a evidencia terminal resumida.

## O que nao fazer

- Nao substituir `review-workflow` ou `security-engineer`.
- Nao usar autofix amplo como comportamento padrao.
- Nao criar wrapper local se o script oficial do repo ja cobre a necessidade.
- Nao recomendar ferramentas internas da central (`validate-skills.py` ou `validate-agent-protocols.py`) fora da própria árvore-fonte da central.

## Perguntas que esta skill responde bem

- "Qual e o menor comando canonico para validar isso?"
- "Essa falha e de codigo ou de ambiente?"
- "Como valido as skills e agents projetados no consumidor?"

## Atalhos uteis

- Executar todos os gates repo-native:
  `pre-commit run --all-files`
- Validar skills, agents e workflows projetados:
  `harness-validate --request .agents/validation/request.json`

## Exemplos e guia amplo

- [examples.md](./examples.md): pedidos concretos e resposta esperada da skill.
- Diretrizes do verifier repo-native, contrato de gates e integridade de evidencia no repositorio.
