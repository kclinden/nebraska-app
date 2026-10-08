#!/usr/bin/env bash
# Checks that this machine has what the Makefile needs and prints how to fix anything missing.
# Usage: scripts/check_setup.sh [local] [aws] [azure] [gcp]   (no args = all)
set -uo pipefail

AWS_PROFILE="${AWS_PROFILE:-master}"
MIN_TERRAFORM="1.6.0"
MIN_PYTHON="3.9.0"

if [[ -t 1 ]]; then
  GREEN=$'\033[32m' YELLOW=$'\033[33m' RED=$'\033[31m' BOLD=$'\033[1m' DIM=$'\033[2m' RESET=$'\033[0m'
else
  GREEN="" YELLOW="" RED="" BOLD="" DIM="" RESET=""
fi

failures=0
warnings=0

if [[ "$(uname -s)" == "Darwin" ]]; then
  PKG="brew install"
  PKG_CASK="brew install --cask"
else
  PKG="sudo apt-get install -y"
  PKG_CASK="see vendor docs:"
fi

ok()   { printf '  %s✔%s %-28s %s%s%s\n' "$GREEN" "$RESET" "$1" "$DIM" "${2:-}" "$RESET"; }
warn() { printf '  %s!%s %-28s %s\n      %sfix:%s %s\n' "$YELLOW" "$RESET" "$1" "$2" "$BOLD" "$RESET" "$3"; warnings=$((warnings + 1)); }
fail() { printf '  %s✘%s %-28s %s\n      %sfix:%s %s\n' "$RED" "$RESET" "$1" "$2" "$BOLD" "$RESET" "$3"; failures=$((failures + 1)); }
section() { printf '\n%s%s%s\n' "$BOLD" "$1" "$RESET"; }

# version_ge 1.7.0 1.6.0 -> true
version_ge() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]]; }

need() {
  local cmd=$1 fix=$2
  if command -v "$cmd" >/dev/null 2>&1; then
    return 0
  fi
  fail "$cmd" "not installed" "$fix"
  return 1
}

check_terraform() {
  need terraform "$PKG hashicorp/tap/terraform  (brew tap hashicorp/tap first)" || return
  local v
  v=$(terraform version -json 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["terraform_version"])' 2>/dev/null)
  if version_ge "${v:-0}" "$MIN_TERRAFORM"; then
    ok terraform "$v"
  else
    fail terraform "version ${v:-unknown} < $MIN_TERRAFORM" "brew upgrade hashicorp/tap/terraform"
  fi
}

check_local() {
  section "Local development (make local-up)"

  need git "$PKG git" && ok git "$(git --version | awk '{print $3}')"
  need make "xcode-select --install  (macOS) or $PKG make" && ok make "$(make --version | head -1)"
  need curl "$PKG curl" && ok curl "$(curl --version | head -1 | awk '{print $2}')"

  if need python3 "$PKG python@3.12"; then
    local v
    v=$(python3 -c 'import platform;print(platform.python_version())')
    if version_ge "$v" "$MIN_PYTHON"; then ok python3 "$v"; else fail python3 "version $v < $MIN_PYTHON" "$PKG python@3.12"; fi
  fi

  if need docker "$PKG_CASK docker  (Docker Desktop) or install Colima: $PKG colima docker"; then
    ok docker "$(docker --version | awk '{print $3}' | tr -d ,)"
    if docker info >/dev/null 2>&1; then
      ok "docker daemon" "running"
      if [[ "$(docker buildx inspect 2>&1)" == *linux/amd64* ]]; then
        ok "docker buildx (linux/amd64)" "available"
      else
        warn "docker buildx (linux/amd64)" "amd64 builds unavailable" "enable 'Use Rosetta for x86/amd64 emulation' in Docker Desktop settings"
      fi
    else
      fail "docker daemon" "not running" "open -a Docker  (or: colima start)"
    fi
    if docker compose version >/dev/null 2>&1; then
      ok "docker compose" "$(docker compose version --short)"
    else
      fail "docker compose" "plugin missing" "update Docker Desktop, or $PKG docker-compose"
    fi
  fi

  if curl -s -o /dev/null -m 10 -w '%{http_code}' https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/158 | grep -q '^200'; then
    ok "ESPN API reachable" "scores can be refreshed"
  else
    warn "ESPN API reachable" "no response" "check network/VPN; make scores keeps the existing app/scores.json"
  fi
}

check_aws() {
  section "AWS (make aws-*)"
  check_terraform
  if need aws "$PKG awscli"; then
    local v
    v=$(aws --version 2>&1 | awk '{print $1}' | cut -d/ -f2)
    if [[ "$v" == 2.* ]]; then ok "aws cli" "$v"; else fail "aws cli" "version $v (v2 required for SSO)" "$PKG awscli"; fi

    if aws configure list-profiles 2>/dev/null | grep -x "$AWS_PROFILE" >/dev/null; then
      ok "aws profile" "$AWS_PROFILE"
      if AWS_PROFILE="$AWS_PROFILE" aws sts get-caller-identity >/dev/null 2>&1; then
        ok "aws sso session" "active"
      else
        warn "aws sso session" "expired or not logged in" "aws sso login --profile $AWS_PROFILE  (make aws-login does this)"
      fi
    else
      fail "aws profile" "'$AWS_PROFILE' not configured" "aws configure sso --profile $AWS_PROFILE  (or set AWS_PROFILE=<name>)"
    fi
  fi
}

check_azure() {
  section "Azure (make azure-*)"
  check_terraform
  if need az "$PKG azure-cli"; then
    ok "az cli" "$(PYTHONWARNINGS=ignore az version --query '"azure-cli"' -o tsv 2>/dev/null)"
    if PYTHONWARNINGS=ignore az account get-access-token -o none >/dev/null 2>&1; then
      ok "az login" "$(PYTHONWARNINGS=ignore az account show --query name -o tsv 2>/dev/null)"
    else
      warn "az login" "not logged in or token expired" "az login  (make azure-login does this)"
    fi
  fi
}

check_gcp() {
  section "GCP (make gcp-*)"
  check_terraform
  if need gcloud "$PKG_CASK google-cloud-sdk"; then
    ok "gcloud" "$(gcloud version --format='value("Google Cloud SDK")' 2>/dev/null)"
    if gcloud auth print-access-token >/dev/null 2>&1; then
      ok "gcloud login" "$(gcloud config get-value account 2>/dev/null)"
    else
      warn "gcloud login" "not logged in" "gcloud auth login  (make gcp-login does this)"
    fi
    if gcloud auth application-default print-access-token >/dev/null 2>&1; then
      ok "application default creds" "present (used by Terraform)"
    else
      warn "application default creds" "missing" "gcloud auth application-default login"
    fi
    local project
    project=$(gcloud config get-value project 2>/dev/null)
    if [[ -n "$project" ]]; then
      ok "gcloud project" "$project"
    else
      fail "gcloud project" "not set" "gcloud config set project <project-id>"
    fi
  fi
}

check_optional() {
  section "Optional"
  if command -v gh >/dev/null 2>&1; then
    if gh auth status >/dev/null 2>&1; then ok "gh (GitHub CLI)" "logged in"; else warn "gh (GitHub CLI)" "not logged in" "gh auth login"; fi
  else
    warn "gh (GitHub CLI)" "not installed (only needed for PRs/workflow runs)" "$PKG gh"
  fi
}

targets=("$@")
[[ ${#targets[@]} -eq 0 ]] && targets=(local aws azure gcp)

printf '%sNebraska App - developer setup check%s\n' "$BOLD" "$RESET"
for t in "${targets[@]}"; do
  case "$t" in
    local) check_local ;;
    aws) check_aws ;;
    azure) check_azure ;;
    gcp) check_gcp ;;
    *) echo "Unknown section '$t' (use local, aws, azure, gcp)" >&2; exit 2 ;;
  esac
done
check_optional

printf '\n'
if ((failures > 0)); then
  printf '%s%d problem(s)%s and %d warning(s). Fix the items marked ✘ and re-run.\n' "$RED" "$failures" "$RESET" "$warnings"
  exit 1
fi
printf '%sAll required tools are ready%s (%d warning(s)).\n' "$GREEN" "$RESET" "$warnings"
