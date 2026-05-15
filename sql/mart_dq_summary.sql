-- DQ summary mart
CREATE OR REPLACE VIEW mart_dq_summary AS
SELECT
    run_id,
    run_timestamp,
    check_name,
    severity,
    status,
    affected_rows,
    message,
    source_file,
    business_date,
    affected_column
FROM dq_issues
ORDER BY
    CASE severity
        WHEN 'critical' THEN 1
        WHEN 'warning'  THEN 2
        ELSE 3
    END,
    run_timestamp DESC;
