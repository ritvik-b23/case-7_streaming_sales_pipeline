-- Daily revenue mart
CREATE OR REPLACE VIEW mart_daily_revenue AS
SELECT
    business_date,
    COUNT(*)                        AS orders_count,
    COUNT(DISTINCT customer_id)     AS unique_customers,
    ROUND(SUM(gross_revenue), 2)    AS gross_revenue,
    ROUND(SUM(discount_amount), 2)  AS discount_amount,
    ROUND(SUM(net_revenue), 2)      AS net_revenue,
    ROUND(AVG(net_revenue), 2)      AS avg_order_value
FROM fact_sales_orders
GROUP BY business_date
ORDER BY business_date;
