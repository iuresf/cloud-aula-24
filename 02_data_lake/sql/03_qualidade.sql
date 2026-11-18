SELECT pedido_id, COUNT(*) AS n FROM pedidos GROUP BY pedido_id HAVING COUNT(*) > 1;
SELECT COUNT(*) AS pedidos_distintos FROM pedidos;
SELECT p.pedido_id FROM pedidos p LEFT JOIN pagamentos pg ON p.pedido_id=pg.pedido_id WHERE pg.pedido_id IS NULL;
