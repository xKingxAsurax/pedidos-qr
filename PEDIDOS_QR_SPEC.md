# Sistema de pedidos por QR para restaurantes — Especificación (v2)

## Cómo usar este archivo

1. Esta carpeta es el proyecto. La especificación vive en `PEDIDOS_QR_SPEC.md`.
2. Se construye por fases. La Fase 1 no incluye el panel de caja ni las fases siguientes.
3. Al terminar cada fase: correr las pruebas, hacer un commit y responder 5 preguntas sobre lo construido antes de seguir.

## Objetivo

Aplicación web para un restaurante pequeño en Colombia. Hay tres formas de pedir:

1. El cliente escanea un QR (en la mesa o para llevar), arma su pedido y recibe un código de 4 dígitos que dice en caja para confirmarlo.
2. El personal toma el pedido directamente (caja o mesero), para clientes sin celular o sin datos.
3. Domicilio: el cliente arma el pedido en la página y lo envía por WhatsApp con su número de pedido y código.

## Stack

- Python 3.11 + Flask, SQLAlchemy y SQLite (suficiente para un piloto con un solo restaurante).
- HTML + Tailwind CSS (diseño responsive: primero celular, también PC).
- Actualización en vivo del panel: empezar con consulta cada 5 segundos (polling). No usar WebSockets en la primera versión.
- Moneda: pesos colombianos (COP), guardar precios como enteros, sin decimales.

## Roles

1. **Cliente (sin cuenta):** pide en mesa, para llevar o a domicilio. No se registra.
2. **Caja / mesero:** inicia sesión, confirma pedidos con el código, toma pedidos directamente, agrega ítems a pedidos ya confirmados y cambia estados.
3. **Administrador:** todo lo anterior, más gestionar menú, precios, disponibilidad, mesas, códigos QR, usuarios y ver el registro de cambios.

## Origen del pedido

Cada pedido guarda de dónde vino: `cliente_qr`, `caja`, `mesero` o `domicilio_web`.

## Flujo 1: pedido en mesa o para llevar con QR

1. El QR de cada mesa abre `/mesa/<numero>` (el QR para llevar abre `/llevar`).
2. El cliente ve el menú por categorías y agrega productos a un carrito, con notas opcionales.
3. Al enviar, el sistema:
   - valida los precios en el servidor (nunca confiar en precios que manda el navegador),
   - guarda el pedido en estado `pendiente_confirmacion`,
   - genera un código de 4 dígitos y se lo muestra en pantalla con el resumen,
   - lo marca para expirar en 15 minutos.
4. El cliente va a caja y dice el código. Caja busca el pedido por código, revisa el contenido y lo confirma.
5. Solo al confirmar pasa a `confirmado` y aparece en la vista de preparación.
6. Estados: `pendiente_confirmacion` → `confirmado` → `en_preparacion` → `listo` → `entregado`, o `cancelado` / `expirado`.

### Reglas del código de 4 dígitos

- Debe ser único entre los pedidos que estén pendientes y no hayan expirado (si hay colisión, generar otro).
- Un pedido que expira sin confirmar pasa a `expirado` y nunca llega a cocina.
- Límite de pedidos por dispositivo/IP en una ventana corta (por ejemplo, máximo 3 pendientes a la vez), para evitar bromas o spam.
- Caja solo puede confirmar pedidos del día y que no hayan expirado.

## Flujo 2: pedido tomado por el personal (sin celular o sin datos)

- Pantalla "Nuevo pedido" en el panel de caja/mesero: elige tipo (mesa, llevar o domicilio por teléfono), mesa si aplica, y agrega productos con cantidad y notas.
- Como lo crea una persona autenticada, **no necesita código**: nace en estado `confirmado` y va directo a preparación.
- El mesero puede usar esta misma pantalla desde un celular o tablet, de pie junto a la mesa.
- Se guarda quién lo creó (`creado_por`) y el origen (`caja` o `mesero`).

## Flujo 3: domicilio por WhatsApp

1. El cliente entra a `/domicilio`, arma el pedido y llena nombre, teléfono y dirección (la dirección se pide en el formulario para evitar errores al copiarla por chat).
2. El sistema guarda el pedido como `pendiente_confirmacion` con número y código de 4 dígitos, y muestra un botón "Enviar por WhatsApp".
3. El botón abre WhatsApp del negocio con un mensaje prellenado, por ejemplo: "Hola, hice el pedido #N, código XXXX" (enlace `https://wa.me/57NUMERO?text=...`).
4. El negocio busca el pedido en el panel por número o código, revisa los datos, confirma con el cliente por el chat y decide el método de pago (efectivo o transferencia) y el costo del domicilio.
5. Caja marca el pedido como `confirmado` y registra el método de pago. El mensaje del cliente puede editarse, por eso la información que vale es la del pedido en el sistema, no la del chat.
6. Expiración: 30 minutos si nadie lo confirma.
- No hay cuenta de Google ni pasarela de pago. El pago lo decide y lo cobra el negocio.

## Flujo 4: agregar ítems a un pedido confirmado

- Caja/mesero abre el pedido y pulsa "Agregar ítems" mientras esté en `confirmado`, `en_preparacion` o `listo` (no cuando ya está `entregado`).
- Los ítems agregados se guardan con una marca de ronda (`ronda` = 2, 3, ...), quién los agregó y cuándo, y el total se recalcula.
- La vista de preparación resalta los ítems nuevos ("AGREGADO") para que cocina no los pase por alto.
- Quitar ítems o cancelar un pedido confirmado solo puede hacerlo el administrador, con un motivo obligatorio.
- Todo cambio se guarda en el registro de cambios (quién, cuándo, qué cambió).

## Modelo de datos (inicial)

- `usuarios(id, usuario, password_hash, rol)` — rol: `caja`, `mesero` o `admin`.
- `mesas(id, numero, activa)`
- `categorias(id, nombre, orden)`
- `productos(id, categoria_id, nombre, descripcion, precio_cop, disponible, imagen_url)`
- `pedidos(id, tipo, origen, mesa_id, codigo, estado, nombre_cliente, telefono, direccion, metodo_pago, costo_domicilio_cop, total_cop, creado_por, creado_en, expira_en, confirmado_en, confirmado_por)` — tipo: `mesa`, `llevar`, `domicilio`; `metodo_pago` puede quedar vacío hasta que caja lo defina.
- `pedido_items(id, pedido_id, producto_id, nombre_snapshot, precio_snapshot_cop, cantidad, nota, ronda, agregado_por, agregado_en)` — guardar nombre y precio al momento del pedido.
- `pedido_cambios(id, pedido_id, usuario_id, accion, detalle, motivo, creado_en)` — registro de cambios para evitar disputas y detectar errores o fraudes internos.

## Seguridad y datos personales

- Contraseñas con hash (nunca en texto plano). Sesiones seguras y protección CSRF en formularios.
- Todas las rutas de caja, mesero y administrador requieren inicio de sesión y verifican el rol.
- Validar en el servidor cantidades, productos disponibles y precios, también en los pedidos que toma el personal.
- No exponer datos de otros clientes en ninguna vista pública.
- Mostrar un aviso corto de tratamiento de datos (nombre, teléfono, dirección) y guardar solo lo necesario. Revisar con el restaurante los requisitos de la Ley 1581 de 2012 de protección de datos antes de operar con clientes reales.
- Servir todo por HTTPS en producción.

## Fases

### Fase 1 — Menú y pedido del cliente (QR)

Menú público por categorías, carrito, creación del pedido, código de 4 dígitos, expiración. Pruebas automáticas: precios validados en el servidor, unicidad del código, expiración.

### Fase 2 — Panel de caja

Login, lista de pendientes con búsqueda por código, confirmar o cancelar, cambio de estados, actualización cada 5 segundos, sonido al llegar un pedido confirmado. Incluye la pantalla "Nuevo pedido" para que el personal tome pedidos directamente.

### Fase 3 — Agregar ítems y registro de cambios

Agregar ítems a pedidos confirmados con rondas, resaltado en la vista de preparación, recálculo del total, permisos del administrador para quitar o cancelar, tabla de cambios.

### Fase 4 — Panel de administrador

Crear, editar y desactivar categorías y productos, marcar producto como agotado, gestión de mesas, generar e imprimir el QR de cada mesa, usuarios del personal.

### Fase 5 — Domicilio por WhatsApp

Formulario de domicilio, número y código de pedido, botón con mensaje prellenado, confirmación y método de pago definidos por caja.

### Fase 6 — Despliegue y piloto

Publicar en un servicio con HTTPS, copias de seguridad de la base de datos, prueba de carga ligera con varios celulares a la vez, piloto de 2 semanas en un solo restaurante.

## Lo que NO se hace en esta versión

- Pagos en línea con tarjeta o pasarelas.
- Cuentas obligatorias para el cliente (ni Google Login).
- API oficial de WhatsApp ni bot que responda automáticamente (solo el enlace con mensaje prellenado).
- App móvil nativa.
- Facturación electrónica.

## Criterios de aceptación de cada fase

- Funciona en un celular real, con datos móviles.
- Las pruebas automáticas pasan.
- Puedo explicar con mis palabras cada archivo y cada decisión.
