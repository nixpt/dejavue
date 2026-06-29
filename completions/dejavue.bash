# dejavue bash completion
# Install: dejavue completion bash | sudo tee /etc/bash_completion.d/dejavue
# Or per-user: dejavue completion bash >> ~/.bash_completion
_dejavue() {
    local cur prev words
    _init_completion || return
    local cmds="version init start changed decision state handoff context status \
check archive roster config install-skill log blame note since changelog ingest recall \
worthiness get list annotate stats promote import export reference link search \
diff timeline tag note-commit completion rejected trap incident invariant pattern entities capabilities branch merge-summary squash-summary epoch milestone explain"
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$cmds" -- "$cur"))
        return
    fi
    local subcmd="${COMP_WORDS[1]}"
    case "$subcmd" in
        decision)
            COMPREPLY=($(compgen -W "--reason --rejected --agent --type --tag --supersedes --durability --confidence --entity --artifacts" -- "$cur"))
            if [[ "$prev" == "--type" ]]; then
                COMPREPLY=($(compgen -W "decision blocker claim question experiment checkpoint" -- "$cur"))
            elif [[ "$prev" == "--durability" ]]; then
                COMPREPLY=($(compgen -W "temporary tactical strategic constitutional" -- "$cur"))
            elif [[ "$prev" == "--confidence" ]]; then
                COMPREPLY=($(compgen -W "speculative proposed experimental adopted deprecated verified" -- "$cur"))
            fi ;;
        trap|incident|invariant|pattern) COMPREPLY=($(compgen -W "--agent --tag --entity" -- "$cur")) ;;
        note)
            COMPREPLY=($(compgen -W "--agent --tag --type --entity --confidence" -- "$cur"))
            if [[ "$prev" == "--type" ]]; then
                COMPREPLY=($(compgen -W "note blocker claim question observation" -- "$cur"))
            elif [[ "$prev" == "--confidence" ]]; then
                COMPREPLY=($(compgen -W "speculative proposed experimental adopted deprecated verified" -- "$cur"))
            fi ;;
        start)    COMPREPLY=($(compgen -W "--agent --goal" -- "$cur")) ;;
        state)    COMPREPLY=($(compgen -W "--summary --agent" -- "$cur")) ;;
        handoff)  COMPREPLY=($(compgen -W "--summary --next --agent" -- "$cur")) ;;
        context)  COMPREPLY=($(compgen -W "--lines" -- "$cur")) ;;
        since)    COMPREPLY=($(compgen -W "--agent --format" -- "$cur")) ;;
        log)      COMPREPLY=($(compgen -W "--since --agent --type --oneline --limit" -- "$cur")) ;;
        recall|search)
                  COMPREPLY=($(compgen -W "--since --agent --type --semantic --limit" -- "$cur")) ;;
        get)      COMPREPLY=($(compgen -W "state handoff decisions context references" -- "$cur")) ;;
        annotate) COMPREPLY=($(compgen -W "state handoff decisions" -- "$cur")) ;;
        check)    COMPREPLY=($(compgen -W "--fix" -- "$cur")) ;;
        archive)  COMPREPLY=($(compgen -W "--before --dry-run" -- "$cur")) ;;
        export)
            COMPREPLY=($(compgen -W "--format --target" -- "$cur"))
            if [[ "$prev" == "--format" ]]; then
                COMPREPLY=($(compgen -W "json md" -- "$cur"))
            elif [[ "$prev" == "--target" ]]; then
                COMPREPLY=($(compgen -W "claude codex gemini copilot cursor all" -- "$cur"))
            fi ;;
        capabilities)
            COMPREPLY=($(compgen -W "--format" -- "$cur"))
            if [[ "$prev" == "--format" ]]; then
                COMPREPLY=($(compgen -W "json text" -- "$cur"))
            fi ;;
        branch)   COMPREPLY=($(compgen -W "start summary close --base --goal --summary --next --agent" -- "$cur")) ;;
        merge-summary) COMPREPLY=($(compgen -f -- "$cur")) ;;
        squash-summary) COMPREPLY=($(compgen -W "--base" -- "$cur")) ;;
        epoch)    COMPREPLY=($(compgen -W "begin end list --summary --agent" -- "$cur")) ;;
        milestone) COMPREPLY=($(compgen -W "--summary --agent" -- "$cur")) ;;
        explain)  COMPREPLY=($(compgen -f -- "$cur")) ;;
        import)   COMPREPLY=($(compgen -f -- "$cur")) ;;
        promote)
            COMPREPLY=($(compgen -W "--to" -- "$cur"))
            if [[ "$prev" == "--to" ]]; then
                COMPREPLY=($(compgen -W "planning" -- "$cur"))
            fi ;;
        diff)     COMPREPLY=($(compgen -W "--format" -- "$cur"))
            if [[ "$prev" == "--format" ]]; then
                COMPREPLY=($(compgen -W "text patch" -- "$cur"))
            fi ;;
        timeline) COMPREPLY=($(compgen -W "--since --width" -- "$cur")) ;;
        config)   COMPREPLY=($(compgen -W "list get set unset" -- "$cur")) ;;
        reference) COMPREPLY=($(compgen -W "list create update view" -- "$cur"))
            if [[ "$prev" == "create" || "$prev" == "update" ]]; then
                COMPREPLY=($(compgen -W "--type --tags" -- "$cur"))
            fi ;;
        tag)      COMPREPLY=($(compgen -W "list filter" -- "$cur")) ;;
        ingest)   COMPREPLY=($(compgen -W "--since --agent --dry-run" -- "$cur")) ;;
        completion) COMPREPLY=($(compgen -W "bash zsh fish" -- "$cur")) ;;
        install-skill) COMPREPLY=($(compgen -W "--dir --force" -- "$cur")) ;;
        init)     COMPREPLY=($(compgen -W "--wizard --force --map --no-hook" -- "$cur")) ;;
    esac
}
complete -F _dejavue dejavue
