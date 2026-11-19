#!/bin/sh
# Installed by scripts/check_push_snapshot.py --install.
# pre-commit runs this migration-mode hook before its own pre-push hooks and
# passes it Git's complete list of ref updates, which those hooks never see;
# its failure fails the push. Every update that publishes commits the remote
# lacks must push the checked-out HEAD. It stores nothing between pushes.
remote=$1
status=0
reject() {
    if [ "$status" -eq 0 ]; then
        printf '%s %s\n' 'FAIL [PUSH_SNAPSHOT]: pre-push checks would not' \
            'validate what this push publishes:' >&2
    fi
    printf '  - %s\n' "$*" >&2
    status=1
}
abort() {
    printf 'ERROR [PUSH_SNAPSHOT]: %s\n' "$*" >&2
    exit 2
}
head=$(git rev-parse --verify --quiet 'HEAD^{commit}') ||
    abort 'cannot resolve the checked-out HEAD'
while IFS= read -r update || [ -n "$update" ]; do
    [ -n "$update" ] || continue
    remote_object=${update##* }
    rest=${update% *}
    remote_ref=${rest##* }
    rest=${rest% *}
    local_object=${rest##* }
    local_ref=${rest% *}
    case $rest in
    *' '*) ;;
    *) abort "malformed ref update: $update" ;;
    esac
    case $local_object$remote_object in
    '' | *[!0-9a-f]*) abort "malformed ref update: $update" ;;
    esac
    case $local_object in
    *[!0]*) ;;
    *) continue ;;
    esac
    target="$local_ref -> $remote_ref"
    if ! commit=$(git rev-parse --verify --quiet "$local_object^{commit}")
    then
        reject "$target does not push a commit"
        continue
    fi
    [ "$commit" = "$head" ] && continue
    known=
    if git cat-file -e "$remote_object^{commit}" 2>/dev/null; then
        known=$remote_object
    fi
    new=$(git rev-list --max-count=1 "$commit" --not "--remotes=$remote" \
        ${known:+"$known"}) || abort "cannot inspect $target"
    if [ -n "$new" ]; then
        pushed=$(git rev-parse --short=12 "$commit")
        checkout=$(git rev-parse --short=12 "$head")
        reject "$target publishes $pushed, not the checked-out HEAD" \
            "$checkout; push each ref from its own clean checkout"
    fi
done
if [ "$status" -ne 0 ]; then
    printf '%s %s\n' 'This push will be rejected. pre-commit still runs its' \
        'hooks first; press Ctrl+C to stop them.' >&2
fi
exit "$status"
