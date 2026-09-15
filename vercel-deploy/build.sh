#!/usr/bin/env bash
# ดึงซอร์ส VBA Academy จาก GitHub แล้ว build เป็นเว็บ static
set -euo pipefail

OWNER="mataarranema-png"
REPO="Spice"
BRANCH="${APP_BRANCH:-claude/vba-interactive-learning-web-yd672k}"
SUBDIR="vba-academy"

echo "==> fetching ${OWNER}/${REPO} @ ${BRANCH}"
rm -rf .source dist
mkdir -p .source

if command -v git >/dev/null 2>&1; then
  git clone --depth 1 --branch "${BRANCH}" "https://github.com/${OWNER}/${REPO}.git" .source
else
  echo "git not found, falling back to tarball"
  curl -fsSL "https://codeload.github.com/${OWNER}/${REPO}/tar.gz/refs/heads/${BRANCH}" -o source.tar.gz
  tar xzf source.tar.gz --strip-components=1 -C .source
fi

if [ ! -d ".source/${SUBDIR}" ]; then
  echo "ERROR: subdir ${SUBDIR} not found" >&2
  ls -la .source >&2
  exit 1
fi

echo "==> installing dependencies"
cd ".source/${SUBDIR}"
npm install --no-audit --no-fund

echo "==> building"
npm run build
cd "${OLDPWD}"

echo "==> collecting output"
cp -r ".source/${SUBDIR}/dist" ./dist
test -f ./dist/index.html || { echo "ERROR: dist/index.html missing" >&2; exit 1; }
ls -la ./dist
echo "==> done"
