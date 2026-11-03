# One command: `make all` -> tests, model run (tables + figures), memo PDF.
PY ?= python3
export PYTHONPATH := src

.PHONY: all test run pdf clean

all: test run pdf

test:
	$(PY) -m pytest -q

run:
	$(PY) -m irrbb.run

# Memo PDF: pandoc (markdown -> HTML with MathML) then headless Chromium print.
pdf:
	pandoc report/alco_memo.md -s --mathml --metadata title="ALCO memo" -c memo.css -o report/alco_memo.html
	node scripts/html_to_pdf.js report/alco_memo.html report/alco_memo.pdf

clean:
	rm -rf outputs/*.csv outputs/*.md outputs/*.json report/figures/*.png report/alco_memo.html
