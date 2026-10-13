#!/usr/bin/env bash
# Cold smoke A: host PATH install → ~/postulaciones → invented sample CV.
# Usage (from repo root, after building a wheel):
#   JOBBOT_SOURCE=wheel:/tmp/jobbot-wheels/jobbot-0.1.0-py3-none-any.whl ./scripts/smoke-cold-home.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${HOME:?HOME must be set}"
WS="${HOME_DIR}/postulaciones"

echo "== install jobbot on PATH =="
bash "${ROOT}/scripts/install.sh"
export PATH="${HOME_DIR}/.local/bin:${PATH}"
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(uv tool dir --bin 2>/dev/null || true)"
  [[ -n "${UV_BIN}" ]] && export PATH="${UV_BIN}:${PATH}"
fi
command -v jobbot
jobbot version

echo "== cold folder ${WS} =="
rm -rf "${WS}"
mkdir -p "${WS}"
cd "${WS}"
jobbot init
test -f "${WS}/.jobbot.toml"
test -f "${WS}/.local/profile.yaml"

echo "== import sample CV =="
python3 -c "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from tests.fixtures.cv_pdf import write_sample_cv; write_sample_cv(Path(sys.argv[2]))" "${ROOT}" "${WS}/cv.pdf"
jobbot profile import-pdf "${WS}/cv.pdf" --promote
jobbot profile validate
NAME="$(python3 -c "import yaml; print(yaml.safe_load(open('.local/profile.yaml'))['personal']['name'])")"
echo "profile name: ${NAME}"
test "${NAME}" = "Marta Soto Vera"

jobbot cv build --target ats || true

echo "== walk-up from subdirectory =="
mkdir -p "${WS}/notas"
cd "${WS}/notas"
jobbot profile validate

echo "OK smoke-cold-home (${WS})"
