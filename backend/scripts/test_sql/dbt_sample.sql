
{{ config(
    materialized='table',
    tags=['daily', 'sales']
) }}

WITH customer_orders AS (
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        c.email,
        o.order_id,
        o.order_date,
        o.status
    FROM 
        {{ ref('customers') }} c
    JOIN 
        {{ ref('orders') }} o ON c.customer_id = o.customer_id
    WHERE 
        o.status != 'canceled'
),

order_items AS (
    SELECT
        order_id,
        SUM(quantity) as total_items,
        SUM(quantity * price) as order_value
    FROM 
        {{ ref('order_items') }}
    GROUP BY 
        order_id
)

SELECT
    co.customer_id,
    co.first_name,
    co.last_name,
    co.email,
    co.order_id,
    co.order_date,
    co.status,
    oi.total_items,
    oi.order_value
FROM 
    customer_orders co
JOIN 
    order_items oi ON co.order_id = oi.order_id
