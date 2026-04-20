#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN="${ROOT}/parabix-devel/build-coverage/bin/icgrep"
PROFILE_DIR="${SCRIPT_DIR}/profiles-targeted"
LOG="${SCRIPT_DIR}/new-tests.log"
SUPPORTING_FILES="${SCRIPT_DIR}/supporting-files"

pass_count=0
fail_count=0

mkdir -p "${PROFILE_DIR}"
find "${PROFILE_DIR}" -name '*.profraw' -delete
: > "${LOG}"

check_exit() {
    local expected="$1"
    local observed="$2"
    if [[ "${expected}" == "NONZERO" ]]; then
        [[ "${observed}" -ne 0 ]]
    else
        [[ "${observed}" -eq "${expected}" ]]
    fi
}

check_text() {
    local expected="$1"
    local file="$2"
    if [[ "${expected}" == "__ANY__" ]]; then
        return 0
    fi
    if [[ "${expected}" == "__EMPTY__" ]]; then
        [[ ! -s "${file}" ]]
        return
    fi
    grep -Fq -- "${expected}" "${file}"
}

run_case() {
    local id="$1"
    local expected_exit="$2"
    local expected_stdout="$3"
    local expected_stderr="$4"
    local command_string="$5"
    local stdout_file
    local stderr_file
    local observed_exit
    local result="PASS"

    stdout_file="$(mktemp)"
    stderr_file="$(mktemp)"

    (
        export LLVM_PROFILE_FILE="${PROFILE_DIR}/${id}-%p-%m.profraw"
        bash -lc "${command_string}"
    ) >"${stdout_file}" 2>"${stderr_file}"
    observed_exit=$?

    if ! check_exit "${expected_exit}" "${observed_exit}"; then
        result="FAIL"
    fi
    if ! check_text "${expected_stdout}" "${stdout_file}"; then
        result="FAIL"
    fi
    if ! check_text "${expected_stderr}" "${stderr_file}"; then
        result="FAIL"
    fi

    if [[ "${result}" == "PASS" ]]; then
        pass_count=$((pass_count + 1))
    else
        fail_count=$((fail_count + 1))
    fi

    {
        echo "## ${id}"
        echo "- command: \`${command_string}\`"
        echo "- expected exit: ${expected_exit}"
        echo "- observed exit: ${observed_exit}"
        echo "- result: ${result}"
        echo
        echo "stdout:"
        echo '```text'
        cat "${stdout_file}"
        echo '```'
        echo
        echo "stderr:"
        echo '```text'
        cat "${stderr_file}"
        echo '```'
        echo
    } >> "${LOG}"

    rm -f "${stdout_file}" "${stderr_file}"
}

run_case \
    "files_with_match" \
    "0" \
    "supporting-files/recursive/alpha.txt" \
    "__EMPTY__" \
    "\"${BIN}\" -l Parabix \"${SUPPORTING_FILES}/recursive/alpha.txt\" \"${SUPPORTING_FILES}/recursive/gamma.txt\""

run_case \
    "files_without_match" \
    "1" \
    "supporting-files/recursive/alpha.txt" \
    "__EMPTY__" \
    "\"${BIN}\" -L ZZZ_NOMATCH \"${SUPPORTING_FILES}/recursive/alpha.txt\" \"${SUPPORTING_FILES}/recursive/gamma.txt\""

run_case \
    "quiet_mode" \
    "0" \
    "__EMPTY__" \
    "__EMPTY__" \
    "\"${BIN}\" -q Parabix \"${SUPPORTING_FILES}/recursive/alpha.txt\""

run_case \
    "numbered_max_count" \
    "0" \
    "1:Parabix alpha" \
    "__EMPTY__" \
    "\"${BIN}\" -n -m=1 Parabix \"${SUPPORTING_FILES}/recursive/alpha.txt\""

run_case \
    "pattern_file" \
    "0" \
    "Parabix" \
    "__EMPTY__" \
    "\"${BIN}\" -f \"${SUPPORTING_FILES}/patterns.txt\" \"${SUPPORTING_FILES}/recursive/alpha.txt\""

run_case \
    "recursive_include" \
    "0" \
    "alpha.txt" \
    "__EMPTY__" \
    "\"${BIN}\" -l -r -include=*.txt Parabix \"${SUPPORTING_FILES}/recursive\""

run_case \
    "recursive_exclude_without_match" \
    "0" \
    "gamma.txt" \
    "__EMPTY__" \
    "\"${BIN}\" -L -r -exclude=*.skip Parabix \"${SUPPORTING_FILES}/recursive\""

run_case \
    "stdin_label" \
    "0" \
    "stdin-label:1:Parabix" \
    "__EMPTY__" \
    "printf 'Parabix\nother\n' | \"${BIN}\" -H -n --label=stdin-label Parabix"

run_case \
    "conflicting_binary_options" \
    "NONZERO" \
    "__EMPTY__" \
    "Conflicting options for binary files" \
    "\"${BIN}\" -a -I Parabix \"${SUPPORTING_FILES}/recursive/alpha.txt\""

run_case \
    "unsupported_binary_mode" \
    "NONZERO" \
    "__EMPTY__" \
    "Sorry, -U is not yet supported." \
    "\"${BIN}\" -U Parabix \"${SUPPORTING_FILES}/recursive/alpha.txt\""

run_case \
    "unsupported_byte_offset" \
    "NONZERO" \
    "__EMPTY__" \
    "Sorry, -b is not yet supported." \
    "\"${BIN}\" -b Parabix \"${SUPPORTING_FILES}/recursive/alpha.txt\""

run_case \
    "unsupported_unix_byte_offsets" \
    "NONZERO" \
    "__EMPTY__" \
    "Sorry, -u is not yet supported." \
    "\"${BIN}\" -u Parabix \"${SUPPORTING_FILES}/recursive/alpha.txt\""

run_case \
    "unsupported_only_matching" \
    "NONZERO" \
    "__EMPTY__" \
    "Sorry, -o is not yet supported." \
    "\"${BIN}\" -o Parabix \"${SUPPORTING_FILES}/recursive/alpha.txt\""

run_case \
    "unsupported_line_buffered" \
    "NONZERO" \
    "__EMPTY__" \
    "Sorry, -line-buffered is not yet supported." \
    "\"${BIN}\" --line-buffered Parabix \"${SUPPORTING_FILES}/recursive/alpha.txt\""

{
    echo "## Summary"
    echo "- passes: ${pass_count}"
    echo "- failures: ${fail_count}"
} >> "${LOG}"

if [[ "${fail_count}" -ne 0 ]]; then
    exit 1
fi
