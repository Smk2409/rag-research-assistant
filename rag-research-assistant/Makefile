.PHONY: test lint validate deploy destroy demo
test:      ; python -m pytest tests -q
validate:  ; sam validate --lint
deploy:    ; ./deploy.sh
destroy:   ; ./destroy.sh
demo:      ; python scripts/offline_demo.py $(FILE) "$(Q)"
serve:     ; cd frontend && python -m http.server 8080
