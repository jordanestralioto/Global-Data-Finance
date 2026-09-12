#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT_DIR="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT_DIR" ]]; then
  printf "[modularizar-guard] ERROR: Could not resolve the repository root from %s\n" "$SCRIPT_DIR" >&2
  exit 1
fi
DEFAULT_PLAN_TEMPLATE="${SCRIPT_DIR}/../references/PLAN_TEMPLATE.md"

log() {
  printf "[modularizar-guard] %s\n" "$1"
}

fail() {
  printf "[modularizar-guard] ERROR: %s\n" "$1" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage:
  bash .agents/skills/modularizar/scripts/modularizar_guard.sh init-plan [--plan PATH] [--template PATH] [--task NAME] [--author NAME] [--target PATH] [--ticket REF] [--force]
  bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-plan --phase phase1|phase1-complete|phase2 [--plan PATH] [--target PATH]
  bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-report [--report PATH] [--target PATH] [--plan PATH]

Commands:
  init-plan       Create modularizar_<target-basename>.md from PLAN_TEMPLATE and prefill metadata.
  validate-plan   Validate phase gates in modularizar_<target-basename>.md.
  validate-report Validate the final modularizar_<target-basename>-output.md evidence file.

Defaults:
  --template: ${DEFAULT_PLAN_TEMPLATE}
  --plan:     derived from --target as modularizar_<target-basename>.md
  --report:   derived from --target as modularizar_<target-basename>-output.md
EOF
}

derive_plan_file_from_target() {
  local target_path="$1"
  local target_name

  target_name="${target_path##*/}"
  target_name="${target_name%.*}"

  [[ -n "$target_name" ]] || return 1

  printf "%s/modularizar_%s.md" "$ROOT_DIR" "$target_name"
}

derive_report_file_from_target() {
  local target_path="$1"
  local target_name

  target_name="${target_path##*/}"
  target_name="${target_name%.*}"

  [[ -n "$target_name" ]] || return 1

  printf "%s/modularizar_%s-output.md" "$ROOT_DIR" "$target_name"
}

derive_report_file_from_plan() {
  local plan_path="$1"
  local plan_name

  plan_name="${plan_path##*/}"
  plan_name="${plan_name%.md}"
  plan_name="${plan_name#modularizar_}"

  [[ -n "$plan_name" ]] || return 1

  printf "%s/modularizar_%s-output.md" "$ROOT_DIR" "$plan_name"
}

derive_plan_file_from_report() {
  local report_path="$1"
  local report_dir
  local report_name

  report_dir="$(dirname "$report_path")"
  report_name="${report_path##*/}"
  report_name="${report_name%-output.md}"

  [[ -n "$report_name" ]] || return 1

  printf "%s/%s.md" "$report_dir" "$report_name"
}

resolve_plan_file() {
  local plan_file="$1"
  local plan_explicit="$2"
  local target_path="$3"

  if [[ "$plan_explicit" == "true" ]]; then
    [[ -n "$plan_file" ]] || fail "--plan requires a path"
    printf "%s" "$plan_file"
    return 0
  fi

  if [[ -n "$target_path" ]]; then
    derive_plan_file_from_target "$target_path"
    return 0
  fi

  fail "Provide --target to derive modularizar_<target-basename>.md or pass --plan explicitly."
}

resolve_report_file() {
  local report_file="$1"
  local report_explicit="$2"
  local target_path="$3"
  local plan_path="$4"

  if [[ "$report_explicit" == "true" ]]; then
    [[ -n "$report_file" ]] || fail "--report requires a path"
    printf "%s" "$report_file"
    return 0
  fi

  if [[ -n "$target_path" ]]; then
    derive_report_file_from_target "$target_path"
    return 0
  fi

  if [[ -n "$plan_path" ]]; then
    derive_report_file_from_plan "$plan_path"
    return 0
  fi

  fail "Provide --target to derive modularizar_<target-basename>-output.md or pass --report explicitly."
}

escape_sed_replacement() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\//\\/}"
  value="${value//&/\\&}"
  printf "%s" "$value"
}

replace_first_exact_line() {
  local file="$1" old_line="$2" new_line="$3"
  local escaped_old escaped_new
  # shellcheck disable=SC2016
  escaped_old="$(printf '%s' "$old_line" | sed 's/[.[\*^$()+?{|\/]/\\&/g')"
  escaped_new="$(escape_sed_replacement "$new_line")"
  sed -i "0,/^${escaped_old}$/s//${escaped_new}/" "$file"
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "File not found: $path"
}

require_line_regex() {
  local file="$1"
  local regex="$2"
  local message="$3"
  grep -Eq "$regex" "$file" || fail "$message"
}

reject_line_regex() {
  local file="$1"
  local regex="$2"
  local message="$3"
  if grep -Eq "$regex" "$file"; then
    fail "$message"
  fi
}

extract_section_block() {
  local file="$1"
  local start_line="$2"
  local end_line="$3"

  awk -v start_line="$start_line" -v end_line="$end_line" '
    $0 == start_line { in_section = 1 }
    in_section {
      if ($0 == end_line && $0 != start_line) {
        exit
      }
      print
    }
  ' "$file"
}

extract_block_from_text() {
  local text="$1"
  local start_line="$2"
  local boundary_regex="$3"

  printf "%s\n" "$text" | awk -v start_line="$start_line" -v boundary_regex="$boundary_regex" '
    $0 == start_line { in_block = 1 }
    in_block {
      if ($0 ~ boundary_regex && $0 != start_line) {
        exit
      }
      print
    }
  '
}

require_section_regex() {
  local section_text="$1"
  local regex="$2"
  local message="$3"

  printf "%s\n" "$section_text" | grep -Eq "$regex" || fail "$message"
}

section_matches_regex() {
  local section_text="$1"
  local regex="$2"

  printf "%s\n" "$section_text" | grep -Eq "$regex"
}

extract_field_value_from_text() {
  local text="$1"
  local field_name="$2"

  printf "%s\n" "$text" | sed -n "s#^- ${field_name}:[[:space:]]*##p" | head -n 1
}

extract_field_value_from_file() {
  local file="$1"
  local field_name="$2"
  extract_field_value_from_text "$(cat "$file")" "$field_name"
}

collect_backticked_values_from_text() {
  local text="$1"
  # shellcheck disable=SC2016
  printf "%s\n" "$text" | grep -o '`[^`]\+`' | tr -d '`' || true
}

ensure_backticked_paths_or_none() {
  local value="$1"
  local label="$2"

  if [[ "$value" == "none" || "$value" == "not applicable" ]]; then
    return 0
  fi

  local paths
  paths="$(collect_backticked_values_from_text "$value")"
  [[ -n "$paths" ]] || fail "${label} must list backticked file paths or use 'none'"
}

ensure_no_private_basenames() {
  local paths="$1"
  local label="$2"
  local allow_init="$3"

  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    local basename="${path##*/}"
    if [[ "$basename" == _* ]]; then
      if [[ "$allow_init" == "true" && "$basename" == "__init__.py" ]]; then
        continue
      fi
      fail "${label} contains disallowed private basename '${basename}'"
    fi
  done <<< "$paths"
}

validate_extracted_module_files_value() {
  local value="$1"
  local label="$2"

  ensure_backticked_paths_or_none "$value" "$label"
  if [[ "$value" == "none" || "$value" == "not applicable" ]]; then
    return 0
  fi

  ensure_no_private_basenames \
    "$(collect_backticked_values_from_text "$value")" \
    "$label" \
    "false"
}

validate_canonical_entrypoint_value() {
  local value="$1"
  local label="$2"

  ensure_backticked_paths_or_none "$value" "$label"
  local paths
  paths="$(collect_backticked_values_from_text "$value")"
  [[ -n "$paths" ]] || fail "${label} must declare one backticked compatibility entrypoint"
  local count
  count="$(printf "%s\n" "$paths" | sed '/^$/d' | wc -l)"
  [[ "$count" -eq 1 ]] || fail "${label} must declare exactly one compatibility entrypoint"

  ensure_no_private_basenames "$paths" "$label" "true"
}

ensure_backticked_paths_required() {
  local value="$1"
  local label="$2"

  ensure_backticked_paths_or_none "$value" "$label"
  [[ "$value" != "none" && "$value" != "not applicable" ]] || fail "${label} must list backticked file paths"
}

ensure_paths_value_contains_path() {
  local value="$1"
  local required_path="$2"
  local label="$3"
  local paths

  paths="$(collect_backticked_values_from_text "$value")"
  printf "%s\n" "$paths" | grep -Fxq "$required_path" || fail "${label} must include path '${required_path}'"
}

enforce_no_finding_sentinels() {
  local block="$1"
  local block_id="$2"

  if section_matches_regex "$block" "^- Finding status:[[:space:]]*no-finding([[:space:]]|$)"; then
    require_section_regex "$block" "^- Files affected:[[:space:]]+none$" "No-finding inventory items must use 'Files affected: none' for ${block_id}"
    require_section_regex "$block" "^- Contract/import/export impact:[[:space:]]+none$" "No-finding inventory items must use 'Contract/import/export impact: none' for ${block_id}"
    require_section_regex "$block" "^- Risk:[[:space:]]+none material$" "No-finding inventory items must use 'Risk: none material' for ${block_id}"
    require_section_regex "$block" "^- Rollback:[[:space:]]+not applicable$" "No-finding inventory items must use 'Rollback: not applicable' for ${block_id}"
  fi
}

enforce_no_change_sentinels() {
  local block="$1"
  local block_id="$2"

  if section_matches_regex "$block" "^- Execution status:[[:space:]]*no-change([[:space:]]|$)"; then
    require_section_regex "$block" "^- Files changed:[[:space:]]+none$" "No-change report items must use 'Files changed: none' for ${block_id}"
    require_section_regex "$block" "^- Contract/import/export impact:[[:space:]]+none$" "No-change report items must use 'Contract/import/export impact: none' for ${block_id}"
    require_section_regex "$block" "^- Caller migration impact:[[:space:]]+none$" "No-change report items must use 'Caller migration impact: none' for ${block_id}"
    require_section_regex "$block" "^- Public symbol impact:[[:space:]]+none$" "No-change report items must use 'Public symbol impact: none' for ${block_id}"
    require_section_regex "$block" "^- Rollback note:[[:space:]]+not applicable$" "No-change report items must use 'Rollback note: not applicable' for ${block_id}"
  fi
}

collect_matching_lines_from_text() {
  local text="$1"
  local regex="$2"
  printf "%s\n" "$text" | grep -E "$regex" || true
}

ensure_unique_lines() {
  local lines="$1"
  local label="$2"
  local duplicates

  duplicates="$(printf "%s\n" "$lines" | sed '/^$/d' | sort | uniq -d)"
  [[ -z "$duplicates" ]] || fail "$label contains duplicates: $(printf "%s" "$duplicates" | paste -sd ', ' -)"
}

extract_heading_ids_from_text() {
  local text="$1"
  local heading_regex="$2"
  local literal_prefix="$3"
  local headings

  headings="$(collect_matching_lines_from_text "$text" "$heading_regex")"

  while IFS= read -r heading; do
    [[ -n "$heading" ]] || continue
    printf "%s\n" "${heading#"$literal_prefix"}"
  done <<< "$headings"
}

require_ids_to_match_plan() {
  local observed_ids="$1"
  local planned_ids="$2"
  local label="$3"

  while IFS= read -r observed_id; do
    [[ -n "$observed_id" ]] || continue
    printf "%s\n" "$planned_ids" | grep -Fxq "$observed_id" || fail "$label '$observed_id' is not declared in the plan"
  done <<< "$observed_ids"
}

validate_heading_blocks_in_section() {
  local section_text="$1"
  local section_name="$2"
  local heading_regex="$3"
  local heading_prefix="$4"
  local boundary_regex="$5"
  shift 5

  local -a rules=("$@")
  local headings
  headings="$(collect_matching_lines_from_text "$section_text" "$heading_regex")"
  [[ -n "$headings" ]] || fail "$section_name must include at least one block"
  ensure_unique_lines "$headings" "$section_name"

  while IFS= read -r heading; do
    [[ -n "$heading" ]] || continue
    local block
    block="$(extract_block_from_text "$section_text" "$heading" "$boundary_regex")"

    for rule in "${rules[@]}"; do
      local regex="${rule%%|||*}"
      local message="${rule#*|||}"
      require_section_regex "$block" "$regex" "$message for ${heading#"$heading_prefix"}"
    done

    enforce_no_finding_sentinels "$block" "${heading#"$heading_prefix"}"
    enforce_no_change_sentinels "$block" "${heading#"$heading_prefix"}"
  done <<< "$headings"
}

validate_common_plan_contract() {
  local plan_file="$1"

  reject_line_regex "$plan_file" "^- .*(<target-basename>|<file-or-module>).*$" "Plan still contains unresolved template placeholders in required fields"
  require_line_regex "$plan_file" "^- Task name:[[:space:]]+.+$" "Task name is missing in plan"
  require_line_regex "$plan_file" "^- Date:[[:space:]]+.+$" "Date is missing in plan"
  require_line_regex "$plan_file" "^- Author agent:[[:space:]]+.+$" "Author agent is missing in plan"
  require_line_regex "$plan_file" "^- Target module/file:[[:space:]]+.+$" "Target module/file is missing in plan"
  require_line_regex "$plan_file" "^- Workflow type:[[:space:]]+.+$" "Workflow type is missing in plan"

  require_line_regex "$plan_file" "^## 3\\. Contract and Migration Baseline" "Contract baseline section is missing"
  require_line_regex "$plan_file" "^- Current public imports/exports:[[:space:]]+.+$" "Current public imports/exports is missing"
  require_line_regex "$plan_file" "^- Callers that must be updated:[[:space:]]+.+$" "Callers that must be updated is missing"
  require_line_regex "$plan_file" "^- Compatibility/migration strategy:[[:space:]]+.+$" "Compatibility/migration strategy is missing"
  require_line_regex "$plan_file" "^- Symbols that may become public:[[:space:]]+.+$" "Symbols that may become public is missing"
}

validate_phase1_plan() {
  local plan_file="$1"

  validate_common_plan_contract "$plan_file"

  require_line_regex "$plan_file" "^## 4\\. Phase 1A - Deep Remediation Proposal" "Phase 1A section is missing"
  require_line_regex "$plan_file" "^- Current responsibilities mixed in the target:[[:space:]]+.+$" "Phase 1 target baseline responsibilities are missing"
  require_line_regex "$plan_file" "^- Main pain points:[[:space:]]+.+$" "Phase 1 target baseline pain points are missing"
  require_line_regex "$plan_file" "^- Expected outcome after cleanup:[[:space:]]+.+$" "Phase 1 target baseline expected outcome is missing"
  require_line_regex "$plan_file" "^### 4\\.2 Internal duplicates" "Internal duplicates inventory is missing"
  require_line_regex "$plan_file" "^### 4\\.3 Shared utility reuse or justified new shared utility" "Shared utility replacement inventory is missing"
  require_line_regex "$plan_file" "^### 4\\.4 Complexity and Big-O optimization" "Complexity and Big-O inventory is missing"
  require_line_regex "$plan_file" "^### 4\\.5 Comment cleanup" "Comment cleanup inventory is missing"
  require_line_regex "$plan_file" "^### 4\\.6 Naming and visibility" "Naming and visibility inventory is missing"
  require_line_regex "$plan_file" "^### 4\\.7 Caller and contract migrations" "Caller and contract migration inventory is missing"
  require_line_regex "$plan_file" "^- What will change in the target:[[:space:]]+.+$" "Phase 1 change summary for the target is missing"
  require_line_regex "$plan_file" "^- What will change outside the target:[[:space:]]+.+$" "Phase 1 change summary outside the target is missing"
  require_line_regex "$plan_file" "^- Public symbol changes expected:[[:space:]]+.+$" "Phase 1 public symbol changes summary is missing"
  require_line_regex "$plan_file" "^- Validation gates for Phase 1:[[:space:]]+.+$" "Phase 1 validation gate summary is missing"

  local gate1_text
  gate1_text="$(extract_section_block "$plan_file" "### 4.9 Gate 1 approval" "## 5. Phase 1B - Deep Remediation Execution Log")"
  require_section_regex "$gate1_text" "^- GATE_1_APPROVED:[[:space:]]*YES([[:space:]]|$)" "Gate 1 is not approved. Set 'GATE_1_APPROVED: YES'"
  require_section_regex "$gate1_text" "^- Approved at:[[:space:]]+.+$" "Gate 1 approval timestamp is missing"
  require_section_regex "$gate1_text" "^- User notes:[[:space:]]+.+$" "Gate 1 user notes are missing"

  local internal_duplicates_text
  internal_duplicates_text="$(extract_section_block "$plan_file" "### 4.2 Internal duplicates" "### 4.3 Shared utility reuse or justified new shared utility")"
  validate_heading_blocks_in_section "$internal_duplicates_text" "Internal duplicates inventory" "^#### Inventory item P1-INT-" "#### Inventory item " "^#### Inventory item " \
    "^- Finding status:[[:space:]]+(finding|no-finding)([[:space:]]|$)|||Internal duplicates finding status is missing" \
    "^- Location:[[:space:]]+.+$|||Internal duplicates location is missing" \
    "^- Problem:[[:space:]]+.+$|||Internal duplicates problem statement is missing" \
    "^- Proposed change:[[:space:]]+.+$|||Internal duplicates proposed change is missing" \
    "^- Files affected:[[:space:]]+.+$|||Internal duplicates affected files are missing" \
    "^- Contract/import/export impact:[[:space:]]+.+$|||Internal duplicates contract/import/export impact is missing" \
    "^- Risk:[[:space:]]+.+$|||Internal duplicates risk is missing" \
    "^- Validation:[[:space:]]+.+$|||Internal duplicates validation is missing" \
    "^- Rollback:[[:space:]]+.+$|||Internal duplicates rollback is missing"

  local shared_utility_text
  shared_utility_text="$(extract_section_block "$plan_file" "### 4.3 Shared utility reuse or justified new shared utility" "### 4.4 Complexity and Big-O optimization")"
  validate_heading_blocks_in_section "$shared_utility_text" "Shared utility reuse inventory" "^#### Inventory item P1-SHARED-" "#### Inventory item " "^#### Inventory item " \
    "^- Finding status:[[:space:]]+(finding|no-finding)([[:space:]]|$)|||Shared utility finding status is missing" \
    "^- Location:[[:space:]]+.+$|||Shared utility location is missing" \
    "^- Existing utility or abstraction to reuse, or why none is sufficient:[[:space:]]+.+$|||Shared utility decision is missing" \
    "^- Future consumers after extraction:[[:space:]]+.+$|||Shared utility future consumers are missing" \
    "^- Problem:[[:space:]]+.+$|||Shared utility problem statement is missing" \
    "^- Proposed change:[[:space:]]+.+$|||Shared utility proposed change is missing" \
    "^- Files affected:[[:space:]]+.+$|||Shared utility affected files are missing" \
    "^- Contract/import/export impact:[[:space:]]+.+$|||Shared utility contract/import/export impact is missing" \
    "^- Risk:[[:space:]]+.+$|||Shared utility risk is missing" \
    "^- Validation:[[:space:]]+.+$|||Shared utility validation is missing" \
    "^- Rollback:[[:space:]]+.+$|||Shared utility rollback is missing"

  local bigo_text
  bigo_text="$(extract_section_block "$plan_file" "### 4.4 Complexity and Big-O optimization" "### 4.5 Comment cleanup")"
  validate_heading_blocks_in_section "$bigo_text" "Complexity and Big-O inventory" "^#### Inventory item P1-BIGO-" "#### Inventory item " "^#### Inventory item " \
    "^- Finding status:[[:space:]]+(finding|no-finding)([[:space:]]|$)|||Complexity and Big-O finding status is missing" \
    "^- Location:[[:space:]]+.+$|||Complexity and Big-O location is missing" \
    "^- Current complexity problem:[[:space:]]+.+$|||Complexity and Big-O current complexity problem is missing" \
    "^- Expected gain:[[:space:]]+.+$|||Complexity and Big-O expected gain is missing" \
    "^- Proposed change:[[:space:]]+.+$|||Complexity and Big-O proposed change is missing" \
    "^- Files affected:[[:space:]]+.+$|||Complexity and Big-O affected files are missing" \
    "^- Contract/import/export impact:[[:space:]]+.+$|||Complexity and Big-O contract/import/export impact is missing" \
    "^- Risk:[[:space:]]+.+$|||Complexity and Big-O risk is missing" \
    "^- Validation:[[:space:]]+.+$|||Complexity and Big-O validation is missing" \
    "^- Rollback:[[:space:]]+.+$|||Complexity and Big-O rollback is missing"

  local comment_text
  comment_text="$(extract_section_block "$plan_file" "### 4.5 Comment cleanup" "### 4.6 Naming and visibility")"
  validate_heading_blocks_in_section "$comment_text" "Comment cleanup inventory" "^#### Inventory item P1-COMMENT-" "#### Inventory item " "^#### Inventory item " \
    "^- Finding status:[[:space:]]+(finding|no-finding)([[:space:]]|$)|||Comment cleanup finding status is missing" \
    "^- Location:[[:space:]]+.+$|||Comment cleanup location is missing" \
    "^- Problem:[[:space:]]+.+$|||Comment cleanup problem statement is missing" \
    "^- Proposed change:[[:space:]]+.+$|||Comment cleanup proposed change is missing" \
    "^- Files affected:[[:space:]]+.+$|||Comment cleanup affected files are missing" \
    "^- Contract/import/export impact:[[:space:]]+.+$|||Comment cleanup contract/import/export impact is missing" \
    "^- Risk:[[:space:]]+.+$|||Comment cleanup risk is missing" \
    "^- Validation:[[:space:]]+.+$|||Comment cleanup validation is missing" \
    "^- Rollback:[[:space:]]+.+$|||Comment cleanup rollback is missing"

  local naming_text
  naming_text="$(extract_section_block "$plan_file" "### 4.6 Naming and visibility" "### 4.7 Caller and contract migrations")"
  validate_heading_blocks_in_section "$naming_text" "Naming and visibility inventory" "^#### Inventory item P1-NAME-" "#### Inventory item " "^#### Inventory item " \
    "^- Finding status:[[:space:]]+(finding|no-finding)([[:space:]]|$)|||Naming and visibility finding status is missing" \
    "^- Location:[[:space:]]+.+$|||Naming and visibility location is missing" \
    "^- Problem:[[:space:]]+.+$|||Naming and visibility problem statement is missing" \
    "^- Proposed change:[[:space:]]+.+$|||Naming and visibility proposed change is missing" \
    "^- Files affected:[[:space:]]+.+$|||Naming and visibility affected files are missing" \
    "^- Contract/import/export impact:[[:space:]]+.+$|||Naming and visibility contract/import/export impact is missing" \
    "^- Risk:[[:space:]]+.+$|||Naming and visibility risk is missing" \
    "^- Validation:[[:space:]]+.+$|||Naming and visibility validation is missing" \
    "^- Rollback:[[:space:]]+.+$|||Naming and visibility rollback is missing"

  local caller_text
  caller_text="$(extract_section_block "$plan_file" "### 4.7 Caller and contract migrations" "### 4.8 Phase 1 change summary")"
  validate_heading_blocks_in_section "$caller_text" "Caller and contract migration inventory" "^#### Inventory item P1-CALLER-" "#### Inventory item " "^#### Inventory item " \
    "^- Finding status:[[:space:]]+(finding|no-finding)([[:space:]]|$)|||Caller and contract migration finding status is missing" \
    "^- Location:[[:space:]]+.+$|||Caller and contract migration location is missing" \
    "^- Problem:[[:space:]]+.+$|||Caller and contract migration problem statement is missing" \
    "^- Proposed change:[[:space:]]+.+$|||Caller and contract migration proposed change is missing" \
    "^- Files affected:[[:space:]]+.+$|||Caller and contract migration affected files are missing" \
    "^- Contract/import/export impact:[[:space:]]+.+$|||Caller and contract migration contract/import/export impact is missing" \
    "^- Risk:[[:space:]]+.+$|||Caller and contract migration risk is missing" \
    "^- Validation:[[:space:]]+.+$|||Caller and contract migration validation is missing" \
    "^- Rollback:[[:space:]]+.+$|||Caller and contract migration rollback is missing"
}

validate_phase1_execution_log() {
  local plan_file="$1"

  require_line_regex "$plan_file" "^## 5\. Phase 1B - Deep Remediation Execution Log" "Phase 1B execution log is missing"
  require_line_regex "$plan_file" "^- PHASE_1_EXECUTED:[[:space:]]*YES([[:space:]]|$)" "Phase 1 must be executed before completion or Phase 2"
  require_line_regex "$plan_file" "^- Phase 1 execution summary:[[:space:]]+.+$" "Phase 1 execution summary is missing"
  require_line_regex "$plan_file" "^- Files changed in Phase 1:[[:space:]]+.+$" "Phase 1 changed files record is missing"
  require_line_regex "$plan_file" "^- Imports/exports migrated in Phase 1:[[:space:]]+.+$" "Phase 1 import/export migration record is missing"
  require_line_regex "$plan_file" "^- Callers migrated in Phase 1:[[:space:]]+.+$" "Phase 1 caller migration record is missing"
  require_line_regex "$plan_file" "^- Public symbols promoted in Phase 1:[[:space:]]+.+$" "Phase 1 public symbol promotion record is missing"
}

validate_phase2_necessity_assessment() {
  local plan_file="$1"
  local expected_decision="$2"

  [[ "$expected_decision" == "YES" || "$expected_decision" == "NO" ]] || fail "Unsupported Phase 2 necessity decision '$expected_decision'"

  require_line_regex "$plan_file" "^### 5\.1 Phase 2 necessity assessment$" "Phase 2 necessity assessment is missing"
  local phase2_necessity_text
  phase2_necessity_text="$(extract_section_block "$plan_file" "### 5.1 Phase 2 necessity assessment" "## 6. Phase 2A - Modularization Proposal")"
  require_section_regex "$phase2_necessity_text" "^- PHASE_2_NEEDED:[[:space:]]*${expected_decision}$" "Phase 2 necessity decision must be ${expected_decision}"
  require_section_regex "$phase2_necessity_text" "^- Residual condition:[[:space:]]*(none|size|complexity|both)$" "Residual condition must be none, size, complexity, or both"
  require_section_regex "$phase2_necessity_text" "^- Structural separation needed:[[:space:]]*(YES|NO)$" "Structural separation decision must be YES or NO"
  require_section_regex "$phase2_necessity_text" "^- Post-Phase 1 size or complexity evidence:[[:space:]]+.+$" "Post-Phase 1 size or complexity evidence is missing"
  require_section_regex "$phase2_necessity_text" "^- Residual structural problem:[[:space:]]+.+$" "Residual structural problem is missing"
  require_section_regex "$phase2_necessity_text" "^- Phase 2 necessity rationale:[[:space:]]+.+$" "Phase 2 necessity rationale is missing"
  if section_matches_regex "$phase2_necessity_text" "^- (Post-Phase 1 size or complexity evidence|Residual structural problem|Phase 2 necessity rationale):[[:space:]]*<[^>]+>"; then
    fail "Phase 2 necessity assessment still contains placeholders"
  fi

  local residual_condition
  local structural_separation
  residual_condition="$(extract_field_value_from_text "$phase2_necessity_text" "Residual condition")"
  structural_separation="$(extract_field_value_from_text "$phase2_necessity_text" "Structural separation needed")"
  if [[ "$expected_decision" == "YES" ]]; then
    [[ "$residual_condition" != "none" ]] || fail "Phase 2 cannot be needed when residual condition is none"
    [[ "$structural_separation" == "YES" ]] || fail "Phase 2 requires structural separation to be YES"
  else
    [[ "$structural_separation" == "NO" ]] || fail "Phase 2 must not be skipped when structural separation is YES"
  fi
}

validate_no_phase2_sections() {
  local plan_file="$1"
  local phase2_text
  local gate2_text

  phase2_text="$(extract_section_block "$plan_file" "## 6. Phase 2A - Modularization Proposal" "## 8. Final Validation Plan")"
  gate2_text="$(extract_section_block "$plan_file" "### 6.4 Gate 2 approval" "## 7. Phase 2B - Modularization Execution Log")"
  require_section_regex "$gate2_text" "^- GATE_2_APPROVED:[[:space:]]*NO$" "Gate 2 must remain NO when Phase 2 is not needed"
  require_section_regex "$phase2_text" "^- PHASE_2_EXECUTED:[[:space:]]*NO$" "Phase 2 must remain unexecuted when it is not needed"

  if section_matches_regex "$gate2_text" "^- (Approved at|User notes):[[:space:]]+.+$"; then
    fail "Gate 2 approval fields must remain blank when Phase 2 is not needed"
  fi
  if section_matches_regex "$phase2_text" "^- (Final public entrypoints|Public entrypoint justification|File naming policy for extracted modules|Canonical compatibility entrypoint|Internal modules and responsibilities|Symbols promoted to public|Promotion justification|Symbols kept internal|Why symbols stay internal|Imports/exports to update|Callers to migrate|Breakages expected after legacy file removal|Legacy files to remove):[[:space:]]+.+$"; then
    fail "Phase 2 proposal fields must remain blank when Phase 2 is not needed"
  fi
  if section_matches_regex "$phase2_text" "^- (Extraction order|Files touched|Extracted module files|Responsibility moved|Public/private symbol impact|Validation checkpoint|Why this step comes now):[[:space:]]+.+$"; then
    fail "Phase 2 extraction steps must remain blank when Phase 2 is not needed"
  fi
  if section_matches_regex "$phase2_text" "^- (Phase 2 execution summary|Files changed in Phase 2|Modules extracted|Canonical compatibility entrypoint used|Imports/exports migrated in Phase 2|Callers migrated in Phase 2|Breakages fixed after legacy file removal|Public symbols promoted in Phase 2|Legacy files removed|Validation evidence for Phase 2|Residual risks after Phase 2):[[:space:]]+.+$"; then
    fail "Phase 2 execution fields must remain blank when Phase 2 is not needed"
  fi
}

validate_phase1_complete_plan() {
  local plan_file="$1"

  validate_phase1_plan "$plan_file"
  validate_phase1_execution_log "$plan_file"
  validate_phase2_necessity_assessment "$plan_file" "NO"
  validate_no_phase2_sections "$plan_file"
}

validate_phase2_plan() {
  local plan_file="$1"

  validate_phase1_plan "$plan_file"

  validate_phase1_execution_log "$plan_file"

  validate_phase2_necessity_assessment "$plan_file" "YES"

  require_line_regex "$plan_file" "^## 6\\. Phase 2A - Modularization Proposal" "Phase 2A section is missing"
  require_line_regex "$plan_file" "^- Final public entrypoints:[[:space:]]+.+$" "Final public entrypoints are missing"
  require_line_regex "$plan_file" "^- Public entrypoint justification:[[:space:]]+.+$" "Public entrypoint justification is missing"
  require_line_regex "$plan_file" "^- File naming policy for extracted modules:[[:space:]]+.+$" "File naming policy for extracted modules is missing"
  require_line_regex "$plan_file" "^- Canonical compatibility entrypoint:[[:space:]]+.+$" "Canonical compatibility entrypoint is missing"
  require_line_regex "$plan_file" "^- Internal modules and responsibilities:[[:space:]]+.+$" "Internal modules and responsibilities are missing"
  require_line_regex "$plan_file" "^- Symbols promoted to public:[[:space:]]+.+$" "Phase 2 promoted public symbols are missing"
  require_line_regex "$plan_file" "^- Promotion justification:[[:space:]]+.+$" "Promotion justification is missing"
  require_line_regex "$plan_file" "^- Symbols kept internal:[[:space:]]+.+$" "Phase 2 internal symbols are missing"
  require_line_regex "$plan_file" "^- Why symbols stay internal:[[:space:]]+.+$" "Internal symbol justification is missing"
  require_line_regex "$plan_file" "^- Imports/exports to update:[[:space:]]+.+$" "Phase 2 import/export migration plan is missing"
  require_line_regex "$plan_file" "^- Callers to migrate:[[:space:]]+.+$" "Phase 2 caller migration plan is missing"
  require_line_regex "$plan_file" "^- Breakages expected after legacy file removal:[[:space:]]+.+$" "Phase 2 legacy removal fallout plan is missing"
  require_line_regex "$plan_file" "^- Legacy files to remove:[[:space:]]+.+$" "Legacy file removal plan is missing"

  local phase2_map_text
  phase2_map_text="$(extract_section_block "$plan_file" "### 6.1 Final module map" "### 6.2 Import and caller migration plan")"
  local target_path
  target_path="$(extract_field_value_from_file "$plan_file" "Target module/file")"
  local naming_policy
  naming_policy="$(extract_field_value_from_text "$phase2_map_text" "File naming policy for extracted modules")"
  section_matches_regex "$naming_policy" "(^|[[:space:];])public-only([[:space:];]|$)" || fail "File naming policy for extracted modules must declare 'public-only'"

  local canonical_entrypoint_value
  canonical_entrypoint_value="$(extract_field_value_from_text "$phase2_map_text" "Canonical compatibility entrypoint")"
  validate_canonical_entrypoint_value "$canonical_entrypoint_value" "Canonical compatibility entrypoint"

  local canonical_entrypoint
  canonical_entrypoint="$(collect_backticked_values_from_text "$canonical_entrypoint_value" | head -n 1)"
  [[ "$canonical_entrypoint" != "$target_path" ]] || fail "Phase 2 plan cannot use the legacy target path as canonical compatibility entrypoint; legacy files must be removed"

  local phase2_migration_text
  phase2_migration_text="$(extract_section_block "$plan_file" "### 6.2 Import and caller migration plan" "### 6.3 Step-by-step extraction sequence")"
  local legacy_files_to_remove_value
  legacy_files_to_remove_value="$(extract_field_value_from_text "$phase2_migration_text" "Legacy files to remove")"
  ensure_backticked_paths_required "$legacy_files_to_remove_value" "Legacy files to remove"
  ensure_paths_value_contains_path "$legacy_files_to_remove_value" "$target_path" "Legacy files to remove"

  local phase2_steps_text
  phase2_steps_text="$(extract_section_block "$plan_file" "### 6.3 Step-by-step extraction sequence" "### 6.4 Gate 2 approval")"
  validate_heading_blocks_in_section "$phase2_steps_text" "Phase 2 extraction sequence" "^#### Planned step P2-STEP-" "#### Planned step " "^#### Planned step " \
    "^- Extraction order:[[:space:]]+.+$|||Phase 2 extraction order is missing" \
    "^- Files touched:[[:space:]]+.+$|||Phase 2 extraction step files are missing" \
    "^- Extracted module files:[[:space:]]+.+$|||Phase 2 extraction step extracted module files are missing" \
    "^- Responsibility moved:[[:space:]]+.+$|||Phase 2 extraction step responsibility is missing" \
    "^- Public/private symbol impact:[[:space:]]+.+$|||Phase 2 extraction step symbol impact is missing" \
    "^- Validation checkpoint:[[:space:]]+.+$|||Phase 2 extraction step validation checkpoint is missing" \
    "^- Why this step comes now:[[:space:]]+.+$|||Phase 2 extraction step ordering rationale is missing"

  local phase2_step_headings
  phase2_step_headings="$(collect_matching_lines_from_text "$phase2_steps_text" "^#### Planned step P2-STEP-")"
  while IFS= read -r heading; do
    [[ -n "$heading" ]] || continue
    local block
    block="$(extract_block_from_text "$phase2_steps_text" "$heading" "^#### Planned step ")"
    local extracted_files_value
    extracted_files_value="$(extract_field_value_from_text "$block" "Extracted module files")"
    local step_id="${heading#\#\#\#\# Planned step }"
    validate_extracted_module_files_value "$extracted_files_value" "Phase 2 plan extracted module files for ${step_id}"
  done <<< "$phase2_step_headings"

  local gate2_text
  gate2_text="$(extract_section_block "$plan_file" "### 6.4 Gate 2 approval" "## 7. Phase 2B - Modularization Execution Log")"
  require_section_regex "$gate2_text" "^- GATE_2_APPROVED:[[:space:]]*YES([[:space:]]|$)" "Gate 2 is not approved. Set 'GATE_2_APPROVED: YES'"
  require_section_regex "$gate2_text" "^- Approved at:[[:space:]]+.+$" "Gate 2 approval timestamp is missing"
  require_section_regex "$gate2_text" "^- User notes:[[:space:]]+.+$" "Gate 2 user notes are missing"
}

validate_phase1_report_against_plan() {
  local plan_file="$1"
  local report_file="$2"
  local plan_phase1_text
  local report_phase1_text
  local plan_ids
  local report_ids

  plan_phase1_text="$(extract_section_block "$plan_file" "### 4.2 Internal duplicates" "### 4.8 Phase 1 change summary")"
  report_phase1_text="$(extract_section_block "$report_file" "### 4.1 Remediation items executed" "### 4.2 Shared utility and deduplication evidence")"

  plan_ids="$(extract_heading_ids_from_text "$plan_phase1_text" "^#### Inventory item P1-" "#### Inventory item ")"
  report_ids="$(extract_heading_ids_from_text "$report_phase1_text" "^#### Executed item P1-" "#### Executed item ")"

  [[ -n "$plan_ids" ]] || fail "Plan does not declare any Phase 1 inventory items"
  [[ -n "$report_ids" ]] || fail "Report does not declare any executed Phase 1 inventory items"

  ensure_unique_lines "$plan_ids" "Phase 1 plan inventory IDs"
  ensure_unique_lines "$report_ids" "Phase 1 report inventory IDs"
  require_ids_to_match_plan "$report_ids" "$plan_ids" "Phase 1 report inventory item"

  while IFS= read -r plan_id; do
    [[ -n "$plan_id" ]] || continue
    local heading="#### Executed item ${plan_id}"
    local block
    block="$(extract_block_from_text "$report_phase1_text" "$heading" "^#### Executed item ")"
    [[ -n "$block" ]] || fail "Phase 1 report is missing block for inventory item ${plan_id}"
    require_section_regex "$block" "^- Inventory item ID:[[:space:]]+${plan_id}$" "Phase 1 report inventory ID line is missing for ${plan_id}"
    require_section_regex "$block" "^- Execution status:[[:space:]]+(executed|no-change)([[:space:]]|$)" "Phase 1 report execution status is missing for ${plan_id}"
    require_section_regex "$block" "^- Files changed:[[:space:]]+.+$" "Phase 1 report changed files are missing for ${plan_id}"
    require_section_regex "$block" "^- Summary:[[:space:]]+.+$" "Phase 1 report summary is missing for ${plan_id}"
    require_section_regex "$block" "^- Contract/import/export impact:[[:space:]]+.+$" "Phase 1 report contract/import/export impact is missing for ${plan_id}"
    require_section_regex "$block" "^- Caller migration impact:[[:space:]]+.+$" "Phase 1 report caller migration impact is missing for ${plan_id}"
    require_section_regex "$block" "^- Public symbol impact:[[:space:]]+.+$" "Phase 1 report public symbol impact is missing for ${plan_id}"
    require_section_regex "$block" "^- Validation evidence:[[:space:]]+.+$" "Phase 1 report validation evidence is missing for ${plan_id}"
    require_section_regex "$block" "^- Rollback note:[[:space:]]+.+$" "Phase 1 report rollback note is missing for ${plan_id}"
    enforce_no_change_sentinels "$block" "${plan_id}"
  done <<< "$plan_ids"
}

validate_phase2_report_against_plan() {
  local plan_file="$1"
  local report_file="$2"
  local plan_phase2_text
  local report_phase2_text
  local plan_ids
  local report_ids

  plan_phase2_text="$(extract_section_block "$plan_file" "### 6.3 Step-by-step extraction sequence" "### 6.4 Gate 2 approval")"
  report_phase2_text="$(extract_section_block "$report_file" "### 5.3 Step execution evidence" "### 5.4 Gate decision")"

  plan_ids="$(extract_heading_ids_from_text "$plan_phase2_text" "^#### Planned step P2-STEP-" "#### Planned step ")"
  report_ids="$(extract_heading_ids_from_text "$report_phase2_text" "^#### Executed step P2-STEP-" "#### Executed step ")"

  [[ -n "$plan_ids" ]] || fail "Plan does not declare any Phase 2 extraction steps"
  [[ -n "$report_ids" ]] || fail "Report does not declare any executed Phase 2 steps"

  ensure_unique_lines "$plan_ids" "Phase 2 plan step IDs"
  ensure_unique_lines "$report_ids" "Phase 2 report step IDs"
  require_ids_to_match_plan "$report_ids" "$plan_ids" "Phase 2 report step"

  while IFS= read -r plan_id; do
    [[ -n "$plan_id" ]] || continue
    local heading="#### Executed step ${plan_id}"
    local block
    block="$(extract_block_from_text "$report_phase2_text" "$heading" "^#### Executed step ")"
    [[ -n "$block" ]] || fail "Phase 2 report is missing block for step ${plan_id}"
    require_section_regex "$block" "^- Step ID:[[:space:]]+${plan_id}$" "Phase 2 report step ID line is missing for ${plan_id}"
    require_section_regex "$block" "^- Execution status:[[:space:]]+(executed|adjusted)([[:space:]]|$)" "Phase 2 report execution status is missing for ${plan_id}"
    require_section_regex "$block" "^- Files changed:[[:space:]]+.+$" "Phase 2 report changed files are missing for ${plan_id}"
    require_section_regex "$block" "^- Extracted module files:[[:space:]]+.+$" "Phase 2 report extracted module files are missing for ${plan_id}"
    require_section_regex "$block" "^- Summary:[[:space:]]+.+$" "Phase 2 report summary is missing for ${plan_id}"
    require_section_regex "$block" "^- Validation evidence:[[:space:]]+.+$" "Phase 2 report validation evidence is missing for ${plan_id}"
    require_section_regex "$block" "^- Rollback note:[[:space:]]+.+$" "Phase 2 report rollback note is missing for ${plan_id}"
    local extracted_files_value
    extracted_files_value="$(extract_field_value_from_text "$block" "Extracted module files")"
    validate_extracted_module_files_value "$extracted_files_value" "Phase 2 report extracted module files for ${plan_id}"
  done <<< "$plan_ids"
}

cmd_init_plan() {
  local template="$DEFAULT_PLAN_TEMPLATE"
  local plan_file=""
  local task_name="Saneamento profundo e modularizacao de god code"
  local author_name="developer-engineer"
  local target_path=""
  local ticket_ref=""
  local force_write="false"
  local plan_explicit="false"

  shift
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --template)
        template="$2"
        shift 2
        ;;
      --plan)
        plan_file="$2"
        plan_explicit="true"
        shift 2
        ;;
      --task)
        task_name="$2"
        shift 2
        ;;
      --author)
        author_name="$2"
        shift 2
        ;;
      --target)
        target_path="$2"
        shift 2
        ;;
      --ticket)
        ticket_ref="$2"
        shift 2
        ;;
      --force)
        force_write="true"
        shift
        ;;
      *)
        fail "Unknown option for init-plan: $1"
        ;;
    esac
  done

  require_file "$template"

  plan_file="$(resolve_plan_file "$plan_file" "$plan_explicit" "$target_path")"

  if [[ -f "$plan_file" && "$force_write" != "true" ]]; then
    fail "Plan already exists at $plan_file. Use --force to overwrite."
  fi

  mkdir -p "$(dirname "$plan_file")"
  cp "$template" "$plan_file"

  local branch_name
  branch_name="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || printf "unknown")"
  local today
  today="$(date +%Y-%m-%d)"

  replace_first_exact_line "$plan_file" "- Task name:" "- Task name: $task_name"
  replace_first_exact_line "$plan_file" "- Date:" "- Date: $today"
  replace_first_exact_line "$plan_file" "- Author agent:" "- Author agent: $author_name"
  replace_first_exact_line "$plan_file" "- Branch:" "- Branch: $branch_name"

  if [[ -n "$target_path" ]]; then
    replace_first_exact_line "$plan_file" "- Target module/file:" "- Target module/file: $target_path"
    local report_file
    report_file="$(derive_report_file_from_target "$target_path")"
    replace_first_exact_line "$plan_file" "- Final report file path: modularizar_<target-basename>-output.md" "- Final report file path: ${report_file##*/}"
    replace_first_exact_line "$plan_file" "- Phase 1-only lock command: \`bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-plan --phase phase1-complete --target <file-or-module>\`" "- Phase 1-only lock command: \`bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-plan --phase phase1-complete --target ${target_path}\`"
    replace_first_exact_line "$plan_file" "- Final lock command: \`bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-report --target <file-or-module>\`" "- Final lock command: \`bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-report --target ${target_path}\`"
  fi

  if [[ -n "$ticket_ref" ]]; then
    replace_first_exact_line "$plan_file" "- Related ticket/issue (if any):" "- Related ticket/issue (if any): $ticket_ref"
  fi

  log "Plan created at $plan_file"
  log "Next step: fill the inventories, get Gate 1 approval, then run validate-plan --phase phase1"
}

cmd_validate_plan() {
  local plan_file=""
  local plan_explicit="false"
  local target_path=""
  local phase=""

  shift
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --plan)
        plan_file="$2"
        plan_explicit="true"
        shift 2
        ;;
      --target)
        target_path="$2"
        shift 2
        ;;
      --phase)
        phase="$2"
        shift 2
        ;;
      *)
        fail "Unknown option for validate-plan: $1"
        ;;
    esac
  done

  [[ -n "$phase" ]] || fail "validate-plan requires --phase phase1|phase1-complete|phase2"
  [[ "$phase" == "phase1" || "$phase" == "phase1-complete" || "$phase" == "phase2" ]] || fail "Unknown phase '$phase'. Use phase1, phase1-complete, or phase2."

  plan_file="$(resolve_plan_file "$plan_file" "$plan_explicit" "$target_path")"

  require_file "$plan_file"

  if [[ "$phase" == "phase1" ]]; then
    validate_phase1_plan "$plan_file"
  elif [[ "$phase" == "phase1-complete" ]]; then
    validate_phase1_complete_plan "$plan_file"
  else
    validate_phase2_plan "$plan_file"
  fi

  if [[ "$phase" == "phase1-complete" ]]; then
    log "PHASE1_COMPLETE=pass ($plan_file)"
  else
    log "${phase^^}_PLAN=pass ($plan_file)"
  fi
}

cmd_validate_report() {
  local report_file=""
  local report_explicit="false"
  local target_path=""
  local plan_path=""

  shift
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --report)
        report_file="$2"
        report_explicit="true"
        shift 2
        ;;
      --target)
        target_path="$2"
        shift 2
        ;;
      --plan)
        plan_path="$2"
        shift 2
        ;;
      *)
        fail "Unknown option for validate-report: $1"
        ;;
    esac
  done

  report_file="$(resolve_report_file "$report_file" "$report_explicit" "$target_path" "$plan_path")"

  require_file "$report_file"
  if [[ -z "$plan_path" ]]; then
    if [[ -n "$target_path" ]]; then
      plan_path="$(resolve_plan_file "" "false" "$target_path")"
    else
      plan_path="$(derive_plan_file_from_report "$report_file")"
    fi
  fi

  require_file "$plan_path"

  reject_line_regex "$report_file" "^- .*(<target-basename>|<file-or-module>).*$" "Report still contains unresolved template placeholders in required fields"
  reject_line_regex "$report_file" "^- .*[[:space:]]pass/fail([[:space:]]|$)" "Report still contains pass/fail placeholders"
  reject_line_regex "$report_file" "^- Refactor status:[[:space:]]*complete/incomplete([[:space:]]|$)" "Report still contains complete/incomplete placeholder"
  require_line_regex "$report_file" "^- GATE_1_APPROVED:[[:space:]]*pass([[:space:]]|$)" "Gate 1 is not marked pass in report"
  require_line_regex "$report_file" "^- PHASE_1_EXECUTED:[[:space:]]*pass([[:space:]]|$)" "Phase 1 is not marked pass in report"
  require_line_regex "$report_file" "^- GATE_2_APPROVED:[[:space:]]*pass([[:space:]]|$)" "Gate 2 is not marked pass in report"
  require_line_regex "$report_file" "^- PHASE_2_EXECUTED:[[:space:]]*pass([[:space:]]|$)" "Phase 2 is not marked pass in report"
  require_line_regex "$report_file" "^- FINAL_VALIDATION:[[:space:]]*pass([[:space:]]|$)" "Final validation is not marked pass in report"
  require_line_regex "$report_file" "^- Gate 1 approval evidence:[[:space:]]+.+$" "Gate 1 approval evidence is missing in report"
  require_line_regex "$report_file" "^- Gate 2 approval evidence:[[:space:]]+.+$" "Gate 2 approval evidence is missing in report"
  require_line_regex "$report_file" "^- Scope changes after approval:[[:space:]]+.+$" "Scope change summary is missing in report"

  require_line_regex "$report_file" "^- Extracted module files:[[:space:]]+.+$" "Extracted module files record is missing in report"
  require_line_regex "$report_file" "^- Canonical compatibility entrypoint used:[[:space:]]+.+$" "Canonical compatibility entrypoint used is missing in report"
  require_line_regex "$report_file" "^- Legacy files removed:[[:space:]]+.+$" "Legacy files removed record is missing in report"
  require_line_regex "$report_file" "^- Public symbols promoted:[[:space:]]+.+$" "Public symbols promoted record is missing in report"
  require_line_regex "$report_file" "^- Import/export migrations applied:[[:space:]]+.+$" "Import/export migration record is missing in report"
  require_line_regex "$report_file" "^- Caller migrations applied:[[:space:]]+.+$" "Caller migration record is missing in report"
  require_line_regex "$report_file" "^- Breakages fixed after legacy file removal:[[:space:]]+.+$" "Legacy removal fallout fix record is missing in report"
  require_line_regex "$report_file" "^- Repo-native validation command:[[:space:]]+.+$" "Repo-native validation command record is missing in report"
  require_line_regex "$report_file" "^- Refactor status:[[:space:]]+(complete|incomplete)([[:space:]]|$)" "Refactor status is missing in report"
  require_line_regex "$report_file" "^- Recommended next action:[[:space:]]+.+$" "Recommended next action is missing in report"

  local plan_phase2_migration_text
  plan_phase2_migration_text="$(extract_section_block "$plan_path" "### 6.2 Import and caller migration plan" "### 6.3 Step-by-step extraction sequence")"
  local target_path
  target_path="$(extract_field_value_from_file "$plan_path" "Target module/file")"
  local plan_legacy_files_to_remove_value
  plan_legacy_files_to_remove_value="$(extract_field_value_from_text "$plan_phase2_migration_text" "Legacy files to remove")"

  local report_phase2_map_text
  report_phase2_map_text="$(extract_section_block "$report_file" "### 5.1 Module map applied" "### 5.2 Migration evidence")"
  local report_extracted_files_value
  report_extracted_files_value="$(extract_field_value_from_text "$report_phase2_map_text" "Extracted module files")"
  validate_extracted_module_files_value "$report_extracted_files_value" "Phase 2 report extracted module files"

  local report_canonical_entrypoint_value
  report_canonical_entrypoint_value="$(extract_field_value_from_text "$report_phase2_map_text" "Canonical compatibility entrypoint used")"
  validate_canonical_entrypoint_value "$report_canonical_entrypoint_value" "Canonical compatibility entrypoint used"
  local report_canonical_entrypoint
  report_canonical_entrypoint="$(collect_backticked_values_from_text "$report_canonical_entrypoint_value" | head -n 1)"
  [[ "$report_canonical_entrypoint" != "$target_path" ]] || fail "Report cannot use the legacy target path as canonical compatibility entrypoint; legacy files must be removed"

  local report_legacy_files_removed_value
  report_legacy_files_removed_value="$(extract_field_value_from_text "$report_phase2_map_text" "Legacy files removed")"
  ensure_backticked_paths_required "$report_legacy_files_removed_value" "Legacy files removed"
  ensure_paths_value_contains_path "$report_legacy_files_removed_value" "$target_path" "Legacy files removed"

  local planned_legacy_paths
  planned_legacy_paths="$(collect_backticked_values_from_text "$plan_legacy_files_to_remove_value")"
  while IFS= read -r planned_legacy_path; do
    [[ -n "$planned_legacy_path" ]] || continue
    ensure_paths_value_contains_path "$report_legacy_files_removed_value" "$planned_legacy_path" "Legacy files removed"
  done <<< "$planned_legacy_paths"

  validate_phase1_report_against_plan "$plan_path" "$report_file"
  validate_phase2_report_against_plan "$plan_path" "$report_file"

  log "FINAL_REPORT=pass ($report_file)"
}

main() {
  local command="${1:-}"
  case "$command" in
    init-plan)
      cmd_init_plan "$@"
      ;;
    validate-plan)
      cmd_validate_plan "$@"
      ;;
    validate-report)
      cmd_validate_report "$@"
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      fail "Unknown command: $command"
      ;;
  esac
}

main "$@"
