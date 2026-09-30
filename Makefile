# Lối tắt cho ./trendvn (mọi việc thật nằm trong ./trendvn, Makefile chỉ gọi nó). `make help` liệt kê lệnh.
# Ví dụ:  make install   make up   make logs S=worker   make logs S=n8n F=1   make backup   make test
S ?= all
N ?= 100

.PHONY: help install up down restart build update status doctor open logs test test-all backup package n8n-build n8n-import n8n-activate agent-logs

help:            ; @./trendvn help
install:         ; @./trendvn install
up:              ; @./trendvn up
down:            ; @./trendvn down
restart:         ; @./trendvn restart
build:           ; @./trendvn build
update:          ; @./trendvn update
status:          ; @./trendvn status
doctor:          ; @./trendvn doctor
open:            ; @./trendvn open
logs:            ; @./trendvn logs $(S) -n $(N) $(if $(F),-f)
agent-logs:      ; @./trendvn logs agent -n $(N) $(if $(F),-f)
test:            ; @./trendvn test
test-all:        ; @./trendvn test all
backup:          ; @./trendvn backup
package:         ; @./trendvn package
n8n-build:       ; @./trendvn n8n build
n8n-import:      ; @./trendvn n8n import
n8n-activate:    ; @./trendvn n8n activate
