// Plantillas de mails. Se renombraron las variables a inglés para alinearlas
// con el payload de la API nueva.
export const templates = {
  'pago-recibido': 'Hola {{name}}, recibimos tu pago de {{amount}}.',
  'pago-vencido': 'Hola {{name}}, tu factura de {{amount}} venció el {{dueDate}}.',
  'bienvenida': 'Hola {{name}}, ya podés entrar al backoffice.',
};
