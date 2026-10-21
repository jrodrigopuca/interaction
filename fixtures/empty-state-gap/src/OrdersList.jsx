export function OrdersList({ orders }) {
  return (
    <table>
      <thead><tr><th>Número</th><th>Fecha</th><th>Total</th><th>Estado</th></tr></thead>
      <tbody>{orders.map((o) => <tr key={o.id}><td>{o.id}</td><td>{o.date}</td><td>{o.total}</td><td>{o.status}</td></tr>)}</tbody>
    </table>
  );
}
