#!/usr/bin/env bash
# Cold smoke B: Docker image → mount ~/postulaciones → invented sample CV.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${HOME:?HOME must be set}"
WS="${HOME_DIR}/postulaciones"

echo "== build image =="
cd "${ROOT}"
docker compose build

echo "== cold folder ${WS} =="
rm -rf "${WS}"
mkdir -p "${WS}"
python3 -c "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from tests.fixtures.cv_pdf import write_sample_cv; write_sample_cv(Path(sys.argv[2]))" "${ROOT}" "${WS}/cv.pdf"

export JOBBOT_HOME="${WS}"
docker compose run --rm jobbot init
test -f "${WS}/.jobbot.toml"
test -f "${WS}/.local/profile.yaml"

docker compose run --rm jobbot profile import-pdf /work/cv.pdf --promote
docker compose run --rm jobbot profile validate

NAME="$(python3 -c "import yaml; print(yaml.safe_load(open('${WS}/.local/profile.yaml'))['personal']['name'])")"
echo "profile name: ${NAME}"
test "${NAME}" = "Marta Soto Vera"

echo "OK smoke-cold-docker (${WS})"
