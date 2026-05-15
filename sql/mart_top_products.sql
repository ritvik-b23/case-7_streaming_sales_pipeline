-- Top products mart
CREATE OR REPLACE VIEW mart_top_products AS
SELECT
    product_id,
    product_name,
    category,
    COUNT(*)                        AS orders_count,
    SUM(qty)                        AS units_sold,
    ROUND(SUM(net_revenue), 2)      AS net_revenue
FROM fact_sales_orders
GROUP BY product_id, product_name, category
ORDER BY net_revenue DESC;
