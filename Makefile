.PHONY: install run-pipeline dashboard test lint clean

install:
	pip install -r requirements.txt

run-pipeline:
	python -m pipeline.run_pipeline --dataset-path "Data for sales"

dashboard:
	streamlit run app/dashboard.py

test:
	pytest tests/ -v

lint:
	ruff check .

clean:
	rm -f data/warehouse/*.duckdb
	rm -f data/dq_reports/*.json
	rm -f data/dq_reports/*.csv
