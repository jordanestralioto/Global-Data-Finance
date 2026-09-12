# Commit em lote CVM tolerante a falhas

**Status:** Aceita
**Data:** 2026-08-31
**Escopo:** extração automática de CSV ZIP CVM para Parquet

> **Parcialmente substituída (2026-09-10):** a decisão de
> [Cutover de ingestão PyArrow e integridade transacional](pyarrow-ingestion-integrity-cutover.md)
> mantém o compromisso failure-atomic, mas substitui este mecanismo CVM-local
> por publicação compartilhada com manifest durável, lock e recuperação.

## Contexto

Um ZIP CVM pode gerar vários Parquets no diretório pertencente ao chamador.
Escrever diretamente no destino permite que a falha do segundo CSV altere ou
apague um Parquet que existia antes da chamada. Usar somente um arquivo
temporário por saída evita corrupção individual, mas ainda expõe um lote
parcialmente atualizado.

## Decisão

`CvmFailureAtomicBatchCommit` é o módulo interno que executa a extração. Ele:

1. valida o ZIP e lista todos os CSVs antes de escrever;
2. rejeita ZIP sem CSV e colisões de basename antes de criar saídas;
3. cria uma área oculta de staging dentro do diretório de destino, garantindo
   o mesmo filesystem;
4. converte todos os CSVs apenas nessa área e valida tamanho, footer e linhas
   dos Parquets staged;
5. cria backup de cada alvo preexistente antes de modificar qualquer alvo,
   preferindo hard link e usando cópia com metadados como fallback;
6. faz `os.replace()` em ordem determinística;
7. em falha, remove saídas novas e restaura backups em ordem reversa;
8. limpa staging e backups somente após commit completo ou rollback normal.

Se a restauração também falhar, a área de recuperação é preservada e o
`ExtractionError` contém o caminho dela, a falha original e a falha de
restauração. Isso evita apagar a única cópia recuperável e mantém a causa
diagnóstica observável.

## Consequências

- O contrato é **commit em lote tolerante a falhas e recuperável**, não uma
  transação multi-arquivo com visibilidade instantaneamente atômica.
- Leitores concorrentes e escritas simultâneas no mesmo destino continuam fora
  de suporte; o diretório pertence ao chamador e pode conter arquivos não
  relacionados, portanto não é substituído como um todo.
- A assinatura pública de `ParquetExtractorAdapterCVM.extract(...)->None`, os
  nomes de saída e os schemas persistidos não mudam.
- Falhas de CSV, disco, validação staged, replace e ZIP corrompido preservam
  os Parquets preexistentes sempre que o rollback normal completa.
