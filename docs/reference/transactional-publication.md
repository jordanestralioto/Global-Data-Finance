# Publicação transacional

A infraestrutura interna `macro_infra/transactional_publication/` publica
artefatos CVM e B3 como um lote recuperável. Os owners de cada fonte continuam
responsáveis por validar conteúdo, schema e contagens antes do commit.
Leitores concorrentes podem observar substituições individuais durante o commit;
a recuperação entrega o lote anterior ou o novo conforme o journal durável.

## Aquisição e recuperação do lock

A aquisição e a remoção de `.globaldatafinance-transaction.lock` usam uma
guarda do sistema operacional, liberada quando seu descritor fecha ou o
processo termina:

- No POSIX, a guarda bloqueia o descritor do diretório de destino.
- No Windows, usa o arquivo privado vazio e persistente
  `.globaldatafinance-publication.guard`. Ele não é resíduo de transação e
  não deve ser removido enquanto houver escritores: os concorrentes precisam
  bloquear o mesmo arquivo.

A guarda protege a janela anterior à persistência de `owner.json` e serializa
tentativas de recuperação. Depois da inicialização, o registro identifica
hostname, PID e `process_started_at`, o início do processo retornado por
`psutil.Process.create_time()`. Esse horário pode variar com ajustes do relógio
do sistema. Um PID vivo com início diferente pode indicar reutilização do PID
ou mudança do relógio; essa diferença não autoriza recuperar a transação.
Qualquer PID vivo, falhas de permissão, identidades inválidas e locks de outro
host bloqueiam a retomada. Um lock com dono identificado só é recuperado
automaticamente quando o PID não existe mais no mesmo host e namespace.
Um lock privado sem dono só é recuperado automaticamente quando está vazio
ou contém apenas temporários
privados de `owner.json`. Conteúdo não reconhecido, aliases e permissões
inseguras são preservados com erro explícito.

A consulta de PID usa `psutil.Process.is_running()`, sem emitir sinais ou
eventos de console no Windows. Falhas de permissão na consulta impedem a
retomada e preservam a causa do diagnóstico.

### Recuperação manual e contêineres

Uma trava antiga sem `process_started_at` continua recuperável quando o PID
não existe; com PID vivo, a biblioteca preserva o comportamento conservador.
PIDs de contêineres diferentes não identificam o mesmo processo. Não trate
ausência de um PID no contêiner atual, idade do arquivo ou mudança de hostname
como prova de que o escritor anterior terminou. Destinos compartilhados
exigem hosts identificáveis e escritores no mesmo namespace de processos
quando usam o mesmo hostname.

Para retomar após interrupção:

1. Pare downloads, extrações e outros escritores do destino, inclusive em
   outros hosts ou contêineres. Confirme no ambiente de origem que o processo
   dono terminou; se isso não for possível, mantenha o destino intacto e use
   um diretório novo.
2. Preserve uma cópia completa do destino, incluindo ZIPs, Parquets,
   `.cvm-write-lock`, `.globaldatafinance-transaction.lock`, manifestos e
   staging. Examine os `owner.json` sem alterar PID, hostname ou timestamps.
3. No fluxo CVM, `.cvm-write-lock` é uma trava externa separada, que exige
   liberação manual após essa confirmação. Se contém somente `owner.json`
   regular e privado, remova apenas esse arquivo e o diretório então vazio.
   Conteúdo adicional, links ou ownership desconhecido exigem inspeção;
   não remova recursivamente a árvore.
4. No mesmo host e namespace, execute novamente a fachada no mesmo destino.
   A trava transacional só é recuperada automaticamente se o PID registrado
   não existir mais; os journals determinam rollback ou conclusão antes de
   começar a nova publicação. Um PID vivo continua bloqueando, mesmo com
   horário de início diferente. Preserve logs se houver erro de recuperação.
5. Se a trava transacional pertence a outro host, tem PID ainda vivo
   (inclusive por reutilização) ou não permite verificar a identidade,
   regenere em um destino novo a partir das fontes preservadas e confira o
   resultado antes de trocar consumidores.
   Esta versão não oferece tomada automática nem comando de recuperação
   forçada entre hosts.

Não apague journals, backups, staging ou o arquivo de guarda Windows para
desbloquear uma publicação; isso pode eliminar a autoridade necessária para
recuperar o lote. A verificação do resultado da fachada continua obrigatória.

## Staging e manifestos

Novas transações criam staging dentro do lock privado, no mesmo filesystem
dos outputs. Os temporários do manifesto ficam dentro do staging. Quedas
anteriores ao primeiro journal ou à promoção do JSON externo deixam os
resíduos dentro de uma árvore com ownership estabelecida pelo lock.

O journal privado continua sendo a autoridade para recuperação dos artefatos;
o JSON externo serve à descoberta. Identidades de diretórios e arquivos,
SHA-256 e verificações de ownership impedem que o registro externo autorize
exclusões de arquivos do chamador. Outputs alterados fora da transação são
preservados. A limpeza remove os filhos antes de `owner.json`, mantendo o
registro se a remoção de um staging for interrompida.

## Compatibilidade e limites

Journals válidos do layout anterior, com staging diretamente no destino,
continuam recuperáveis, inclusive sem o manifesto externo. Diretórios e
temporários antigos sem autoridade verificável permanecem preservados para
inspeção explícita; seus prefixos não autorizam exclusões.

A guarda exige suporte do filesystem ao lock nativo. A fronteira continua
exigindo isolamento do filesystem e excluindo escritores concorrentes hostis
e processos com acesso arbitrário pelo mesmo UID. A recuperação de publicação
também não substitui a inspeção exigida pelo lock externo `.cvm-write-lock`
do fluxo CVM.

Os dados dos arquivos são sincronizados antes da publicação. No Windows,
essa sincronização abre o arquivo com acesso de escrita, exigido pelo CRT.
O `fsync` de diretórios nessa plataforma é tratado como não suportado e gera
aviso; o fluxo não tenta abrir diretórios com a API de arquivos do CRT.
Em plataformas que suportam essa operação, erros de permissão e de I/O
continuam interrompendo a transação. A recuperação de queda do processo não
equivale a uma garantia de durabilidade contra queda de energia em todos os
filesystems.
