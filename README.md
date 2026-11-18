# Curado & Cava

Tienda de charcutería fina (carnes frías, quesos, vinos y maridajes) hecha para el **Proyecto 3** de Programación IV.
Los datos viven en archivos **CSV**, el análisis se hace con **pandas** y el dashboard se dibuja con **Chart.js**.

## Qué hace

- **Catálogo (CRUD en `productos.csv`)**: listar, registrar, comprar y eliminar productos.
- **Compras**: validan el stock, lo descuentan en `productos.csv` y registran la venta en `ventas.csv`.
- **Tablas de charcutería**: tres tablas de la casa (2, 6 y 12 personas) y un armador para que el cliente elija sus ingredientes.
- **Maridajes**: 6 combinaciones de vino y acompañamientos con descuento.
- **Dashboard**: tarjetas de KPIs y tres gráficas que se actualizan solas después de cada compra, alta o baja.
- **Productos por surtir**: calculado con pandas según el stock mínimo y la velocidad de venta.

## Estructura

```
curado_y_cava/
├── main.py            API con FastAPI (CSV, pandas y endpoints)
├── productos.csv      Catálogo e inventario
├── ventas.csv         Historial de ventas y mermas
├── requirements.txt   Librerías necesarias
├── locustfile.py      Pruebas de carga (opcional)
└── frontend/
    ├── index.html     Página de la tienda y dashboard
    ├── style.css      Estilos (paleta vino y oro)
    └── app.js         Consumo de la API con fetch() y gráficas
```

## Cómo correrlo

1. Instalar las librerías: `pip install -r requirements.txt`
2. Iniciar la API (dentro de la carpeta del proyecto): `uvicorn main:app --reload`
3. Abrir la tienda en el navegador: http://127.0.0.1:8000/tienda/
4. Documentación interactiva de la API: http://127.0.0.1:8000/docs

## Endpoints principales

| Método | Ruta | Para qué sirve |
|---|---|---|
| GET | `/productos` | Lista el catálogo (lee `productos.csv`) |
| POST | `/productos` | Registra un producto nuevo (agrega una fila) |
| POST | `/productos/{id}?cantidad=1` | Compra: descuenta stock y registra la venta |
| DELETE | `/productos/{id}` | Elimina el producto y reescribe `productos.csv` |
| GET | `/reportes/kpis` | KPIs: producto más comprado, ingresos, transacciones, ticket promedio |
| GET | `/reportes/ventas-por-producto` | Serie para la gráfica de barras |
| GET | `/reportes/ingresos-por-dia` | Serie para la gráfica de líneas |
| GET | `/reportes/categorias` | Serie para la gráfica de pastel |
| GET | `/reportes/surtir` | Productos por surtir y cuánto pedir |

Además: `/tablas`, `/maridajes`, `/productos/{id}/surtir` y `/productos/{id}/merma`.

## Notas

- `ventas.csv` incluye tres semanas de historial de ejemplo para que el dashboard tenga datos desde el inicio.
- Un candado (`asyncio.Lock`) evita que dos compras a la vez dejen el stock en negativo.
- El limitador de 5 peticiones por segundo está apagado (`LIMITADOR_ACTIVO = False`) para poder probar con Locust.
- Pruebas de carga: `locust -f locustfile.py --host http://127.0.0.1:8000`
