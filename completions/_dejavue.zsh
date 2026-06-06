#compdef dejavue
# dejavue zsh completion
# Install: dejavue completion zsh | sudo tee /usr/share/zsh/site-functions/_dejavue
# Or per-user (fpath must include the dir):
#   dejavue completion zsh > "${fpath[1]}/_dejavue"
_dejavue() {
    local state
    _arguments -C \
        '1: :->subcmd' \
        '*:: :->args' && return 0
    case $state in
        subcmd)
            local subcommands=(
                'version:Print dejavue version'
                'init:Create .dejavue/, install git hooks'
                'start:Record session start'
                'changed:Record file change event'
                'decision:Record architectural decision or blocker/claim/question'
                'state:Overwrite state.md with current snapshot'
                'handoff:Write handoff.md'
                'context:Print boot packet (handoff + state + decisions + events)'
                'status:One-line health view'
                'check:Health check: JSONL, hooks, .gitattributes, FTS'
                'archive:Compact old file_changed events from timeline'
                'roster:Show agent activity summary'
                'config:Get, set, or list per-repo config values'
                'install-skill:Install SKILL.md to your agent skills directory'
                'log:Formatted timeline view with filters'
                'blame:Show decisions and events touching a file path'
                'note:Record a lightweight timestamped note'
                'since:Temporal delta since a date, commit, or agent session'
                'ingest:Scrape .claude/, CHANGELOG, ADRs, git log into timeline'
                'recall:Keyword (FTS5) or semantic search over all artifacts'
                'worthiness:Print the capture/skip worthiness gate'
                'get:Direct fetch of a doc (state, handoff, decisions, context)'
                'list:List available artifacts'
                'annotate:Append timestamped note to a doc without rewriting it'
                'stats:Timeline statistics by type, agent, date range'
                'promote:Graduate .dejavue/ into a richer planning system'
                'import:Bootstrap context.md from an existing AGENTS.md/CLAUDE.md'
                'export:Export memory snapshot or generate DCP adapter files'
                'reference:Manage reference cards in .dejavue/references/'
                'link:Show dejavue events for a git commit SHA'
                'search:Alias for recall — keyword search over all artifacts'
                'diff:Compare dejavue memory between two refs'
                'timeline:ASCII activity chart of events over time'
                'tag:List tags or filter events by tag'
                'note-commit:Write a git note linking a commit to the last dejavue event'
                'completion:Print shell completion script (bash, zsh, fish)'
                'rejected:Show decisions with rejected alternatives, optionally filtered'
                'trap:Record a known lie / trap (misleading name, fake abstraction)'
                'incident:Record an operational incident (outage, corruption, migration)'
                'invariant:Record an architectural invariant that must always hold'
                'pattern:Record a discovered convention/pattern (naming, idiom, structure)'
                'entities:List entities, or show events referencing one entity'
            )
            _describe 'subcommand' subcommands ;;
        args)
            case $words[1] in
                decision)
                    _arguments \
                        '--reason[Why this decision was made]:reason' \
                        '*--rejected[Rejected alternative and reason]:alt:reason' \
                        '--agent[Agent name]:agent' \
                        '--type[Event type]:type:(decision blocker claim question experiment checkpoint)' \
                        '--supersedes[ID or title of a prior decision this supersedes]:event-id' \
                        '--durability[How long-lived this decision is]:durability:(temporary tactical strategic constitutional)' \
                        '--confidence[How firm this decision is]:confidence:(speculative proposed experimental adopted deprecated verified)' \
                        '*--entity[Subject this event is about, repeatable]:entity' \
                        '--tag[Tag]:tag' ;;
                trap|incident|invariant|pattern)
                    _arguments \
                        '--agent[Agent name]:agent' \
                        '*--entity[Subject this event is about, repeatable]:entity' \
                        '--tag[Tag]:tag' ;;
                note)
                    _arguments \
                        '--agent[Agent name]:agent' \
                        '--tag[Tag]:tag' \
                        '*--entity[Subject this event is about, repeatable]:entity' \
                        '--confidence[How firm this note/claim is]:confidence:(speculative proposed experimental adopted deprecated verified)' \
                        '--type[Note type]:type:(note blocker claim question observation)' ;;
                export)
                    _arguments \
                        '--format[Output format]:format:(json md)' \
                        '--target[Adapter target]:target:(claude codex gemini copilot cursor all)' ;;
                promote)
                    _arguments '--to[Target system]:system:(jagent)' ;;
                diff)
                    _arguments '--format[Diff format]:format:(text patch)' ;;
                get)
                    _arguments '1:doc:(state handoff decisions context)' ;;
                annotate)
                    _arguments '1:doc:(state handoff decisions)' ;;
                completion)
                    _arguments '1:shell:(bash zsh fish)' ;;
                config)
                    local config_cmds=('list:List all config values' 'get:Get a value' 'set:Set a value' 'unset:Remove a key')
                    _describe 'config subcommand' config_cmds ;;
                reference)
                    local ref_cmds=('list:List all cards' 'create:Create a card' 'update:Overwrite a card' 'view:Print a card')
                    _describe 'reference subcommand' ref_cmds ;;
                tag)
                    local tag_cmds=('list:List all tags with counts' 'filter:Show events with a tag')
                    _describe 'tag subcommand' tag_cmds ;;
                import)
                    _arguments '1:file:_files' ;;
            esac ;;
    esac
}
_dejavue
