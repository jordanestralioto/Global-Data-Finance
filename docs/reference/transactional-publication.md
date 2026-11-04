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
tentativas de recuperação. Depois da inicialização, o registro continua
rejeitando PIDs vivos e locks de outro host. Um lock privado sem dono só é
recuperado automaticamente quando está vazio ou contém apenas temporários
privados de `owner.json`. Conteúdo não reconhecido, aliases e permissões
inseguras são preservados com erro explícito.

A consulta de PID usa `psutil.Process.is_running()`, sem emitir sinais ou
eventos de console no Windows. Falhas de permissão na consulta impedem a
retomada e preservam a causa do diagnóstico.

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
