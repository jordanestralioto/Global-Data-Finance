# Patterns Reference

Use esta referência como consulta rápida. Cada padrão abaixo inclui o problema que
ele resolve, sinais de uso, custos, disqualifiers, alternativa mais simples e
pré-requisitos para adoção segura.

## Modular Monolith

- **Problema que resolve:** separar domínio, ownership e mudança sem pagar custo de rede.
- **Sinais de uso:** deploy único ainda funciona, mas módulos brigam entre si e a base cresce sem fronteira.
- **Custos operacionais:** disciplina de boundary, contratos internos, revisão de acoplamento.
- **Disqualifiers:** partes exigem deploy independente frequente ou isolamento forte de falha.
- **Alternativa mais simples:** reorganizar módulos e contratos sem refator estrutural grande.
- **Pré-requisitos:** fronteiras nomeadas, imports controlados e ownership claro.

## Worker Isolado / Job Assíncrono

- **Problema que resolve:** trabalho lento, frágil ou com retry próprio sem travar o request principal.
- **Sinais de uso:** provider externo lento, export/import, reconciliação, processamento em lote.
- **Custos operacionais:** fila ou scheduler, idempotência, retries, observabilidade, reconciliação.
- **Disqualifiers:** resposta precisa ser imediata ou o domínio não tolera estado intermediário.
- **Alternativa mais simples:** job interno controlado no mesmo deploy.
- **Pré-requisitos:** contrato de job, estratégia de retry e operação monitorável.

## Microservice

- **Problema que resolve:** boundary forte de deploy, escala, falha e ownership.
- **Sinais de uso:** partes com ritmo de mudança distinto, contratos estáveis e benefício real de autonomia.
- **Custos operacionais:** rede, tracing, versionamento, compatibilidade, deploy, incidentes distribuídos.
- **Disqualifiers:** fronteira ainda confusa, domínio em descoberta ou ausência de capacidade operacional.
- **Alternativa mais simples:** monólito modular ou worker isolado.
- **Pré-requisitos:** contrato explícito, observabilidade mínima e plano de migração incremental.

## Event-Driven Integration

- **Problema que resolve:** desacoplar produtores e consumidores com processamento reativo.
- **Sinais de uso:** múltiplos consumidores, integração assíncrona e tolerância a atraso.
- **Custos operacionais:** ordem, duplicidade, reprocessamento, versionamento de eventos, debugging.
- **Disqualifiers:** necessidade forte de resposta síncrona ou de consistência imediata.
- **Alternativa mais simples:** chamada síncrona ou job com polling previsível.
- **Pré-requisitos:** contrato de evento, idempotência, DLQ/retry e monitoramento.

## CQRS Seletivo

- **Problema que resolve:** leitura e escrita com modelos estruturalmente diferentes.
- **Sinais de uso:** consultas pesadas, projeções especializadas, escrita com invariantes densas.
- **Custos operacionais:** duplicação de modelo, rebuild de projeção, consistência eventual, manutenção extra.
- **Disqualifiers:** CRUD comum ou divergência apenas estética de payload.
- **Alternativa mais simples:** query otimizada, cache, materialized view ou read model local.
- **Pré-requisitos:** motivo claro para separar modelos e estratégia de atualização das projeções.

## Ports & Adapters / Hexagonal

- **Problema que resolve:** reduzir acoplamento com infraestrutura e integrações mutáveis.
- **Sinais de uso:** múltiplos providers, testes de regra de domínio independentes, integração com legado hostil.
- **Custos operacionais:** mais camadas, abstração extra, risco de interface vazia por hábito.
- **Disqualifiers:** sistema pequeno com um único adapter estável e baixa chance de troca.
- **Alternativa mais simples:** integração concreta com seams pontuais.
- **Pré-requisitos:** boundary clara entre domínio e infraestrutura e adapters com responsabilidade real.

## Domain Model / DDD-Lite

- **Problema que resolve:** concentrar invariantes e evitar regra de negócio espalhada.
- **Sinais de uso:** múltiplas regras dependentes, vocabulário de domínio importante e conflitos frequentes de consistência.
- **Custos operacionais:** curva de modelagem, disciplina conceitual e objetos mais ricos.
- **Disqualifiers:** fluxo essencialmente procedural ou CRUD com pouca regra.
- **Alternativa mais simples:** transaction script bem organizado.
- **Pré-requisitos:** linguagem de domínio estável o bastante para sustentar a modelagem.
