
CREATE TABLE dbo.CustomerOrders (
    CustomerID INT PRIMARY KEY,
    OrderID INT NOT NULL,
    OrderDate DATETIME,
    TotalAmount DECIMAL(10,2),
    Region VARCHAR(50),
    CONSTRAINT FK_CustomerOrders_Customers FOREIGN KEY (CustomerID) REFERENCES dbo.Customers(CustomerID)
);

INSERT INTO dbo.CustomerOrders (CustomerID, OrderID, OrderDate, TotalAmount, Region)
SELECT 
    c.CustomerID,
    o.OrderID,
    o.OrderDate,
    SUM(od.Quantity * od.UnitPrice) as TotalAmount,
    c.Region
FROM 
    dbo.Customers c
JOIN 
    dbo.Orders o ON c.CustomerID = o.CustomerID
JOIN 
    dbo.OrderDetails od ON o.OrderID = od.OrderID
WHERE 
    c.Active = 1
GROUP BY 
    c.CustomerID, o.OrderID, o.OrderDate, c.Region;
