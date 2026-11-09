# Patterns Reference

Use esta referência para eliminar opções inadequadas e tornar custos explícitos.
Os sinais resumem o problema; compare o custo e a alternativa menor antes de
adotar o padrão. Os critérios independem de linguagem ou framework.

## Modular Monolith

- **Sinais:** deploy único funciona, mas domínio, ownership e mudanças precisam de fronteiras internas.
- **Custos operacionais:** controlar imports, contratos internos e acoplamento ao longo das mudanças.
- **Disqualifiers:** partes exigem deploy independente frequente ou isolamento forte de falha.
- **Alternativa mais simples:** reorganizar módulos e contratos sem refator estrutural grande.
- **Pré-requisitos:** fronteiras nomeadas, imports controlados e ownership claro.

## Worker Isolado / Job Assíncrono

- **Sinais:** integração lenta, lote ou trabalho com retry próprio prejudica o request principal.
- **Custos operacionais:** fila ou scheduler, idempotência, retries, observabilidade e reconciliação.
- **Disqualifiers:** resposta precisa ser imediata ou o domínio não tolera estado intermediário.
- **Alternativa mais simples:** job interno controlado no mesmo deploy.
- **Pré-requisitos:** contrato de job, estratégia de retry e operação monitorável.

## Microservice

- **Sinais:** contratos estáveis e ganho demonstrado de autonomia de deploy, escala, falha ou ownership.
- **Custos operacionais:** falhas de rede, tracing, compatibilidade, deploys e incidentes distribuídos.
- **Disqualifiers:** fronteira ainda confusa, domínio em descoberta ou ausência de capacidade operacional.
- **Alternativa mais simples:** monólito modular ou worker isolado.
- **Pré-requisitos:** contrato explícito, observabilidade mínima e plano de migração incremental.

## Event-Driven Integration

- **Sinais:** produtores e consumidores precisam evoluir separados e toleram processamento assíncrono.
- **Custos operacionais:** ordem, duplicidade, retenção, reprocessamento e versionamento de eventos.
- **Disqualifiers:** necessidade forte de resposta síncrona ou de consistência imediata.
- **Alternativa mais simples:** chamada síncrona ou job com polling previsível.
- **Pré-requisitos:** contrato de evento, idempotência, DLQ/retry e monitoramento.

## CQRS Seletivo

- **Sinais:** leitura e escrita exigem modelos distintos, com projeções especializadas e invariantes de escrita.
- **Custos operacionais:** modelos duplicados, rebuild e atualização de projeções; atraso se forem assíncronas.
- **Disqualifiers:** CRUD comum ou divergência apenas estética de payload.
- **Alternativa mais simples:** query otimizada, cache, materialized view ou read model local.
- **Pré-requisitos:** motivo claro para separar modelos e estratégia de atualização das projeções.

## Ports & Adapters / Hexagonal

- **Sinais:** regras precisam de testes independentes de infraestrutura ou de isolamento de integrações mutáveis.
- **Custos operacionais:** mais camadas, abstração extra, risco de interface vazia por hábito.
- **Disqualifiers:** abstrações não isolam regra, falha ou variação real e só aumentam indireção.
- **Alternativa mais simples:** integração concreta com seams pontuais.
- **Pré-requisitos:** boundary clara entre domínio e infraestrutura e adapters com responsabilidade real.

## Domain Model / DDD-Lite

- **Sinais:** invariantes densas, regras dependentes e vocabulário de domínio pedem concentração da lógica.
- **Custos operacionais:** curva de modelagem, disciplina conceitual e objetos mais ricos.
- **Disqualifiers:** fluxo essencialmente procedural ou CRUD com pouca regra.
- **Alternativa mais simples:** transaction script bem organizado.
- **Pré-requisitos:** linguagem de domínio estável o bastante para sustentar a modelagem.
