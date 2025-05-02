
CREATE TABLE public.sales_summary (
    product_id INTEGER NOT NULL,
    category_id INTEGER,
    product_name VARCHAR(100),
    total_sales DECIMAL(12,2),
    units_sold INTEGER,
    avg_unit_price DECIMAL(10,2),
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (product_id, year, month),
    FOREIGN KEY (category_id) REFERENCES public.categories(category_id)
);

INSERT INTO public.sales_summary (
    product_id, category_id, product_name, total_sales, 
    units_sold, avg_unit_price, year, month
)
SELECT 
    p.product_id,
    p.category_id,
    p.product_name,
    SUM(s.quantity * s.unit_price) as total_sales,
    SUM(s.quantity) as units_sold,
    AVG(s.unit_price) as avg_unit_price,
    EXTRACT(YEAR FROM s.sale_date) as year,
    EXTRACT(MONTH FROM s.sale_date) as month
FROM 
    public.products p
JOIN 
    public.sales s ON p.product_id = s.product_id
GROUP BY 
    p.product_id, p.category_id, p.product_name, 
    EXTRACT(YEAR FROM s.sale_date), EXTRACT(MONTH FROM s.sale_date);
