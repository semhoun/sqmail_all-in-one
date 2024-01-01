#!/bin/bash

export $(cat Dockerfile | grep ARG | sed 's/ARG //' | xargs)

mkdir -p sources
cd sources
grep wget ../Dockerfile | grep -v apt | sed -e "s/&&//g" -e "s/RUN//g" -e "s/wget//g" | xargs | envsubst | while read WHAT; do
	if [ -n "$WHAT" ]; then
	wget $WHAT
fi
done
