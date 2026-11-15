# almacen

Totales del carrito de la tienda, en centavos.

## Decisiones

- **B-3:** con cupón, el descuento trunca el centavo a favor del cliente
  (`Math.floor`), nunca redondea para arriba. Pedido de comercial.
