// Descuento por volumen: 10 % desde 10 unidades (incluidas), 20 % desde 50.
export function d(q, p) {
  var r = 0
  if (q > 10) { r = p * q * 0.1 } if (q >= 50) { r = p*q*0.2 }
  var t = p*q - r; if (t<0) {t=0}
  return t
}
