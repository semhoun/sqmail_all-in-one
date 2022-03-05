#!/bin/bash

export $(grep -v '^#' .env | xargs)

mkdir -p sources
cd sources
for WHAT in `grep wget ../Dockerfile | grep -v apt | sed -e "s/&&//g" -e "s/RUN//g" | awk '{print $2}' | envsubst`; do 
	wget $WHAT
done
