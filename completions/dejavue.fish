# dejavue fish completion
# Install: dejavue completion fish | source
# Or persist: dejavue completion fish > ~/.config/fish/completions/dejavue.fish
set -l cmds version init start changed decision state handoff context status \
    check archive roster config install-skill log blame note since changelog ingest recall \
    worthiness get list annotate stats promote import export reference link search \
    diff timeline tag note-commit completion rejected trap incident invariant pattern entities capabilities branch merge-summary squash-summary epoch milestone explain conflict
complete -c dejavue -f -n "not __fish_seen_subcommand_from $cmds" -a "$cmds"
# decision / note types
complete -c dejavue -n "__fish_seen_subcommand_from decision" -l type -a "decision blocker claim question experiment checkpoint"
complete -c dejavue -n "__fish_seen_subcommand_from decision" -l durability -a "temporary tactical strategic constitutional"
complete -c dejavue -n "__fish_seen_subcommand_from decision note" -l confidence -a "speculative proposed experimental adopted deprecated verified"
complete -c dejavue -n "__fish_seen_subcommand_from start changed decision state handoff note trap incident invariant pattern branch epoch milestone conflict" -l author-type -a "human agent orchestrator ci bot"
complete -c dejavue -n "__fish_seen_subcommand_from start changed decision state handoff note trap incident invariant pattern branch epoch milestone conflict" -l tension
complete -c dejavue -n "__fish_seen_subcommand_from decision note" -l freshness
complete -c dejavue -n "__fish_seen_subcommand_from decision note" -l expires-after
complete -c dejavue -n "__fish_seen_subcommand_from decision note" -l derived-from
complete -c dejavue -n "__fish_seen_subcommand_from decision note" -l stability -a "ephemeral operational architectural constitutional historical"
complete -c dejavue -n "__fish_seen_subcommand_from decision" -l artifacts -rF
complete -c dejavue -n "__fish_seen_subcommand_from decision" -l supersedes
complete -c dejavue -n "__fish_seen_subcommand_from note" -l type -a "note blocker claim question observation"
# export
complete -c dejavue -n "__fish_seen_subcommand_from export" -l format -a "json md"
complete -c dejavue -n "__fish_seen_subcommand_from export" -l target -a "claude codex gemini copilot cursor all"
# capabilities
complete -c dejavue -n "__fish_seen_subcommand_from capabilities" -l format -a "json text"
# branch / merge-summary
complete -c dejavue -n "__fish_seen_subcommand_from branch" -a "start summary close"
complete -c dejavue -n "__fish_seen_subcommand_from branch" -l base
complete -c dejavue -n "__fish_seen_subcommand_from branch" -l goal
complete -c dejavue -n "__fish_seen_subcommand_from branch" -l summary
complete -c dejavue -n "__fish_seen_subcommand_from branch" -l next
complete -c dejavue -n "__fish_seen_subcommand_from branch" -l agent -d "Agent name"
complete -c dejavue -n "__fish_seen_subcommand_from squash-summary" -l base
# epoch / milestone
complete -c dejavue -n "__fish_seen_subcommand_from epoch" -a "begin end list"
complete -c dejavue -n "__fish_seen_subcommand_from epoch milestone" -l summary
complete -c dejavue -n "__fish_seen_subcommand_from epoch milestone" -l agent -d "Agent name"
complete -c dejavue -n "__fish_seen_subcommand_from explain" -rF
complete -c dejavue -n "__fish_seen_subcommand_from conflict" -a "record list"
complete -c dejavue -n "__fish_seen_subcommand_from conflict" -l path -rF
complete -c dejavue -n "__fish_seen_subcommand_from conflict" -l reason
complete -c dejavue -n "__fish_seen_subcommand_from conflict" -l resolution
complete -c dejavue -n "__fish_seen_subcommand_from conflict" -l agent -d "Agent name"
# promote
complete -c dejavue -n "__fish_seen_subcommand_from promote" -l to -a "planning"
# diff
complete -c dejavue -n "__fish_seen_subcommand_from diff" -l format -a "text patch"
# get / annotate docs
complete -c dejavue -n "__fish_seen_subcommand_from get" -a "state handoff decisions context"
complete -c dejavue -n "__fish_seen_subcommand_from annotate" -a "state handoff decisions"
# sub-subcommands
complete -c dejavue -n "__fish_seen_subcommand_from config" -a "list get set unset"
complete -c dejavue -n "__fish_seen_subcommand_from reference" -a "list create update view"
complete -c dejavue -n "__fish_seen_subcommand_from tag" -a "list filter"
# shell selection
complete -c dejavue -n "__fish_seen_subcommand_from completion" -a "bash zsh fish"
# common flags
complete -c dejavue -n "__fish_seen_subcommand_from decision note start trap incident invariant pattern" -l agent -d "Agent name"
complete -c dejavue -n "__fish_seen_subcommand_from decision note trap incident invariant pattern" -l tag -d "Tag"
complete -c dejavue -n "__fish_seen_subcommand_from decision note trap incident invariant pattern" -l entity -d "Subject (repeatable)"
complete -c dejavue -n "__fish_seen_subcommand_from log recall since" -l since -d "Since date or commit"
complete -c dejavue -n "__fish_seen_subcommand_from check" -l fix -d "Auto-fix issues"
complete -c dejavue -n "__fish_seen_subcommand_from import" -rF
