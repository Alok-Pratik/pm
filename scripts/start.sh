#!/usr/bin/env sh
set -eu

if [ -x /Applications/Docker.app/Contents/Resources/bin/docker ]; then
  PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
  export PATH
fi

docker compose up --build --force-recreate --detach
