#!/usr/bin/env bash
# Import questions from adoorback/assets/questions.tsv into the running DB.
# Run from host (with venv) or copy into the app container working directory.
#
#   ./import_questions_tsv.sh
#   ./import_questions_tsv.sh --skip-duplicates
#   ./import_questions_tsv.sh --path /path/to/other.tsv
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
exec python3 manage.py load_questions "$@"
