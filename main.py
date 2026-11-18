### Autora: Laura Leal; Proyecto 3: Tienda "Curado & Cava" (FastAPI, CSV, pandas y Chart.js)

import asyncio
import csv
import json
import math
import os
import time
from collections import deque
from datetime import datetime
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="API Curado & Cava")

# Lock: solo deja pasar una operación a la vez, así dos clientes no se pisan al leer y escribir los CSV
lock = asyncio.Lock()
# Espera que simula la consulta a una base de datos (segundos)
LATENCIA = 0.05

NOMBRE_TIENDA = "Curado & Cava"
LEMA = "Charcutería fina y maridajes para compartir"


# ====================== ARCHIVOS CSV (productos y ventas) ======================
# No hay listas con productos en el código: cada petición lee productos.csv y, si cambia algo, lo reescribe

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_PRODUCTOS = os.path.join(CARPETA, "productos.csv")
RUTA_VENTAS = os.path.join(CARPETA, "ventas.csv")
CAMPOS_PRODUCTOS = ["id", "categoria", "nombre", "unidad", "precio", "costo", "cantidad", "minimo"]
CAMPOS_VENTAS = [
    "id_venta", "fecha", "tipo", "concepto", "id_producto", "producto",
    "categoria", "cantidad", "precio_unitario", "costo_unitario", "total",
]
# utf-8-sig para que Excel muestre bien los acentos
CODIFICACION = "utf-8-sig"


# Reescribe productos.csv completo con la lista que se le da
def escribir_productos(productos):
    with open(RUTA_PRODUCTOS, "w", newline="", encoding=CODIFICACION) as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_PRODUCTOS)
        escritor.writeheader()
        escritor.writerows(productos)


# Lee productos.csv y regresa una lista de diccionarios con los tipos correctos (si no existe, lo crea vacío)
def leer_productos():
    if not os.path.exists(RUTA_PRODUCTOS):
        escribir_productos([])
    with open(RUTA_PRODUCTOS, newline="", encoding=CODIFICACION) as archivo:
        return [
            {
                "id": int(fila["id"]), "categoria": fila["categoria"], "nombre": fila["nombre"],
                "unidad": fila["unidad"], "precio": float(fila["precio"]), "costo": float(fila["costo"]),
                "cantidad": int(fila["cantidad"]), "minimo": int(fila["minimo"]),
            }
            for fila in csv.DictReader(archivo)
        ]


# Lee los renglones de ventas.csv (lista vacía si el archivo todavía no existe)
def leer_renglones_ventas():
    if not os.path.exists(RUTA_VENTAS):
        return []
    with open(RUTA_VENTAS, newline="", encoding=CODIFICACION) as archivo:
        return list(csv.DictReader(archivo))


# Agrega una venta (o una merma) a ventas.csv, un renglón por producto; regresa el id de la venta
# En una venta el total es lo cobrado (cantidad x precio); en una merma es lo perdido (cantidad x costo)
def registrar_venta(lineas, concepto, tipo="venta"):
    id_venta = max([int(f["id_venta"]) for f in leer_renglones_ventas()] or [0]) + 1
    existe = os.path.exists(RUTA_VENTAS)
    fecha = datetime.now().isoformat(timespec="seconds")

    with open(RUTA_VENTAS, "a", newline="", encoding=CODIFICACION) as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_VENTAS)
        if not existe:
            escritor.writeheader()
        for linea in lineas:
            precio = linea["precio_unitario"] if tipo == "venta" else linea["costo_unitario"]
            escritor.writerow({
                "id_venta": id_venta, "fecha": fecha, "tipo": tipo, "concepto": concepto,
                **linea, "total": round(linea["cantidad"] * precio, 2),
            })
    return id_venta


# El id de un producto nuevo nunca se repite, ni con productos que ya se eliminaron (por el historial de ventas)
def siguiente_id(productos):
    ids_ventas = [int(f["id_producto"]) for f in leer_renglones_ventas()]
    return max([p["id"] for p in productos] + ids_ventas + [0]) + 1


# ====================== RECETAS DE TABLAS Y MARIDAJES ======================
# Esto no es inventario: solo dice qué productos (por id) lleva cada tabla y cada maridaje

# Solo carnes, quesos y acompañamientos van en una tabla (peso = lugar que ocupan; los acompañamientos, la mitad)
PESO_CATEGORIA = {"carne": 1.0, "queso": 1.0, "acompanamiento": 0.5}

# Tamaños de tabla: porciones totales (de 100 g), máximo de ingredientes distintos y precio del servicio de armado
TAMANOS = {
    "pareja": {"nombre": "Tabla para dos", "personas": 2, "porciones": 6, "max_ingredientes": 6, "armado": 90},
    "seis": {"nombre": "Tabla para seis", "personas": 6, "porciones": 18, "max_ingredientes": 10, "armado": 160},
    "doce": {"nombre": "Tabla para doce", "personas": 12, "porciones": 36, "max_ingredientes": 14, "armado": 260},
}
# El costo del armado es el 50 % de lo que se cobra
COSTO_ARMADO = 0.5

# Tablas que la tienda ya tiene armadas
TABLAS_DEFAULT = {
    "pareja": {"nombre": "Tabla Íntima", "tamano": "pareja", "ingredientes": [1, 6, 9, 10, 21, 19]},
    "seis": {"nombre": "Tabla Reunión", "tamano": "seis", "ingredientes": [1, 2, 5, 9, 10, 12, 21, 22]},
    "doce": {"nombre": "Tabla Celebración", "tamano": "doce",
             "ingredientes": [1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 21, 22, 20, 19]},
}

# Maridajes: vino + acompañamientos ({id de producto: cantidad}); se venden con 8 % de descuento
DESCUENTO_MARIDAJE = 0.08
MARIDAJES = [
    {"id": 1, "nombre": "Rosé de Terraza", "tabla_ideal": "pareja", "productos": {17: 1, 21: 2, 22: 1},
     "por_que": "El rosado es ligero y fresco, va bien con el brie y el salami; la fruta limpia el paladar."},
    {"id": 2, "nombre": "Burbujas y Miel", "tabla_ideal": "pareja", "productos": {18: 1, 20: 1, 19: 1},
     "por_que": "Las burbujas cortan la grasa del jamón y los quesos; la miel y el chocolate dan el toque dulce."},
    {"id": 3, "nombre": "Tinto Clásico", "tabla_ideal": "seis", "productos": {15: 2, 22: 2, 19: 1},
     "por_que": "El tinto tiene cuerpo para el serrano, el chorizo y el manchego; el pan equilibra y el chocolate cierra."},
    {"id": 4, "nombre": "Blanco Fresco", "tabla_ideal": "seis", "productos": {16: 2, 21: 3, 20: 1},
     "por_que": "El blanco es ácido y combina con quesos suaves y de cabra; la miel y la fruta suman frescura."},
    {"id": 5, "nombre": "Gran Celebración", "tabla_ideal": "doce", "productos": {18: 3, 19: 3, 21: 4, 20: 1},
     "por_que": "Tres espumosos para brindar con el queso azul y el trufado; fruta y chocolate para el postre."},
    {"id": 6, "nombre": "Selección Sommelier", "tabla_ideal": "doce", "productos": {15: 2, 16: 1, 18: 2, 19: 2, 20: 2, 22: 3},
     "por_que": "Un tinto, un blanco y un espumoso para probar todo: cada vino acompaña carnes, quesos y dulces distintos."},
]


# Reparte las porciones de una tabla entre sus ingredientes: carnes y quesos reciben el doble que
# los acompañamientos y cada ingrediente lleva al menos 1 porción (el resultado suma `total`)
def repartir_porciones(total, categorias):
    pesos = [PESO_CATEGORIA[c] for c in categorias]
    ideal = [total * p / sum(pesos) for p in pesos]
    porciones = [max(1, int(x)) for x in ideal]
    while sum(porciones) < total:
        i = max(range(len(porciones)), key=lambda k: ideal[k] - porciones[k])
        porciones[i] += 1
    while sum(porciones) > total:
        candidatos = [k for k in range(len(porciones)) if porciones[k] > 1]
        if not candidatos:
            break
        i = max(candidatos, key=lambda k: porciones[k] - ideal[k])
        porciones[i] -= 1
    return porciones


# ====================== ANÁLISIS CON PANDAS (lee ventas.csv) ======================

# Lee ventas.csv con pandas y agrega las columnas de día y costo total
def leer_ventas():
    if not os.path.exists(RUTA_VENTAS):
        return pd.DataFrame(columns=CAMPOS_VENTAS + ["dia", "costo_total"])
    ventas = pd.read_csv(RUTA_VENTAS, encoding=CODIFICACION, parse_dates=["fecha"])
    ventas["dia"] = ventas["fecha"].dt.strftime("%Y-%m-%d")
    ventas["costo_total"] = ventas["cantidad"] * ventas["costo_unitario"]
    return ventas


# Solo las ventas (sin mermas); con sin_servicio=True también se quita el "Servicio de armado"
def solo_ventas(sin_servicio=False):
    ventas = leer_ventas()
    ventas = ventas[ventas["tipo"] == "venta"]
    if sin_servicio:
        ventas = ventas[ventas["id_producto"] != 0]
    return ventas


# DataFrame -> lista de diccionarios que FastAPI sí puede convertir a JSON
def a_lista(df):
    return json.loads(df.to_json(orient="records", force_ascii=False))


# KPIs para las tarjetas del dashboard
def calcular_kpis():
    ventas = solo_ventas()
    kpis = {
        "ingresos_totales": 0, "total_transacciones": 0, "ticket_promedio": 0,
        "unidades_vendidas": 0, "producto_mas_comprado": None, "producto_mayor_ingreso": None,
    }
    if ventas.empty:
        return kpis

    por_venta = ventas.groupby("id_venta")["total"].sum()
    por_producto = ventas[ventas["id_producto"] != 0].groupby("producto").agg(
        unidades=("cantidad", "sum"), ingresos=("total", "sum"))

    kpis["ingresos_totales"] = round(float(ventas["total"].sum()), 2)
    kpis["total_transacciones"] = int(por_venta.size)
    kpis["ticket_promedio"] = round(float(por_venta.mean()), 2)
    kpis["unidades_vendidas"] = int(por_producto["unidades"].sum())
    mas_comprado = por_producto["unidades"].idxmax()
    mayor_ingreso = por_producto["ingresos"].idxmax()
    kpis["producto_mas_comprado"] = {"nombre": mas_comprado, "unidades": int(por_producto.loc[mas_comprado, "unidades"])}
    kpis["producto_mayor_ingreso"] = {"nombre": mayor_ingreso, "ingresos": round(float(por_producto.loc[mayor_ingreso, "ingresos"]), 2)}
    return kpis


# Serie para gráfica de barras: unidades e ingresos de cada producto (de mayor a menor ingreso)
def calcular_ventas_por_producto():
    ventas = solo_ventas(sin_servicio=True)
    if ventas.empty:
        return []
    tabla = ventas.groupby("producto").agg(unidades=("cantidad", "sum"), ingresos=("total", "sum"))
    return a_lista(tabla.sort_values("ingresos", ascending=False).round(2).reset_index())


# Serie para gráfica de líneas: ingresos, pérdidas y utilidad de cada día
def calcular_ingresos_por_dia():
    datos = leer_ventas()
    ventas = datos[datos["tipo"] == "venta"]
    mermas = datos[datos["tipo"] == "merma"]
    if ventas.empty:
        return []
    tabla = pd.DataFrame({
        "ingresos": ventas.groupby("dia")["total"].sum(),
        "costo": ventas.groupby("dia")["costo_total"].sum(),
        "ventas": ventas.groupby("dia")["id_venta"].nunique(),
        "perdidas": mermas.groupby("dia")["total"].sum(),
    }).fillna(0)
    tabla["utilidad"] = tabla["ingresos"] - tabla["costo"] - tabla["perdidas"]
    return a_lista(tabla.drop(columns="costo").round(2).reset_index())


# Serie para gráfica de pastel: qué categorías dejan más dinero y con qué margen
def calcular_por_categoria():
    ventas = solo_ventas()
    if ventas.empty:
        return []
    tabla = ventas.groupby("categoria").agg(
        unidades=("cantidad", "sum"), ingresos=("total", "sum"), costo=("costo_total", "sum"))
    tabla["utilidad"] = tabla["ingresos"] - tabla["costo"]
    tabla["margen_pct"] = tabla["utilidad"] / tabla["ingresos"] * 100
    tabla = tabla.drop(columns="costo").sort_values("ingresos", ascending=False)
    return a_lista(tabla.round(2).reset_index())


# Qué productos se pierden más (mermas)
def calcular_perdidas_por_producto():
    mermas = leer_ventas()
    mermas = mermas[mermas["tipo"] == "merma"]
    if mermas.empty:
        return []
    tabla = mermas.groupby("producto").agg(unidades=("cantidad", "sum"), perdida=("total", "sum"))
    return a_lista(tabla.sort_values("perdida", ascending=False).round(2).reset_index())


# Qué hay que surtir y cuánto pedir. Se toma en cuenta el stock mínimo y qué tan rápido se vende:
#   dias_restantes = cuántos días alcanza lo que hay, según el promedio de ventas por día
#   objetivo = lo mayor entre el doble del mínimo y lo que se vende en 14 días
#   surtir = cuántas unidades faltan para llegar al objetivo
def calcular_surtir():
    inv = pd.DataFrame(leer_productos(), columns=CAMPOS_PRODUCTOS)
    datos = leer_ventas()
    ventas = datos[(datos["tipo"] == "venta") & (datos["id_producto"] != 0)]
    vacio = {"productos_a_surtir": [], "inversion_necesaria": 0, "valor_del_inventario_a_costo": 0,
             "valor_del_inventario_a_precio_de_venta": 0}
    if inv.empty:
        return vacio

    dias_periodo = 1
    if not datos.empty:
        dias_periodo = max((datos["fecha"].max() - datos["fecha"].min()).days + 1, 1)
    vendido = ventas.groupby("id_producto")["cantidad"].sum()

    inv["venta_diaria"] = inv["id"].map(vendido).fillna(0) / dias_periodo
    inv["dias_restantes"] = inv["cantidad"] / inv["venta_diaria"].where(inv["venta_diaria"] > 0)
    inv["objetivo"] = [max(m * 2, math.ceil(d * 14)) for m, d in zip(inv["minimo"], inv["venta_diaria"])]
    inv["surtir"] = (inv["objetivo"] - inv["cantidad"]).clip(lower=0)
    inv["costo_estimado"] = inv["surtir"] * inv["costo"]

    urgente = (inv["cantidad"] <= inv["minimo"]) | (inv["dias_restantes"] <= 7)
    pedido = inv[urgente & (inv["surtir"] > 0)].sort_values("dias_restantes", na_position="last")
    columnas = ["id", "nombre", "cantidad", "minimo", "venta_diaria", "dias_restantes", "surtir", "costo_estimado"]
    return {
        "productos_a_surtir": a_lista(pedido[columnas].round(2)),
        "inversion_necesaria": round(float(pedido["costo_estimado"].sum()), 2),
        "valor_del_inventario_a_costo": round(float((inv["cantidad"] * inv["costo"]).sum()), 2),
        "valor_del_inventario_a_precio_de_venta": round(float((inv["cantidad"] * inv["precio"]).sum()), 2),
    }


# ====================== LIMITADOR DE PETICIONES (middleware) ======================

# Apagado para poder hacer pruebas de carga con Locust; ponlo en True para activarlo (máximo 5 por segundo)
LIMITADOR_ACTIVO = False
LIMITE_PETICIONES = 5
VENTANA_SEGUNDOS = 1
tiempos_peticiones = deque()
candado_limitador = asyncio.Lock()


@app.middleware("http")
async def limitar_peticiones(request, call_next):
    if not LIMITADOR_ACTIVO:
        return await call_next(request)
    async with candado_limitador:
        ahora = time.monotonic()
        while tiempos_peticiones and ahora - tiempos_peticiones[0] >= VENTANA_SEGUNDOS:
            tiempos_peticiones.popleft()
        # Si ya hubo 5 peticiones en el último segundo, responde 429 (Too Many Requests)
        if len(tiempos_peticiones) >= LIMITE_PETICIONES:
            return JSONResponse(
                status_code=429,
                content={"detail": "Demasiadas peticiones, máximo 5 por segundo. Intenta de nuevo en un momento."},
                headers={"Retry-After": "1"},
            )
        tiempos_peticiones.append(ahora)
    return await call_next(request)


# CORS: permite que la página (index.html) le hable a esta API sin que el navegador la bloquee
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ====================== MODELOS DE PYDANTIC ======================

# Producto nuevo (si algo no cumple, FastAPI responde 422 solo)
class ProductoNuevo(BaseModel):
    categoria: Literal["carne", "queso", "vino", "acompanamiento", "canasta"]
    nombre: str = Field(min_length=2, description="Nombre del producto")
    unidad: str = "pieza"
    precio: float = Field(gt=0, description="Precio de venta")
    costo: float = Field(ge=0, description="Lo que nos cuesta a nosotros")
    cantidad: int = Field(ge=0)
    minimo: int = Field(default=0, ge=0, description="Stock mínimo antes de tener que surtir")


# Producto perdido: caducado, dañado, etc.
class Merma(BaseModel):
    cantidad: int = Field(ge=1)
    motivo: str = Field(min_length=3)


# Tabla armada por el cliente: tamaño + ids de los productos que eligió
class TablaPersonalizada(BaseModel):
    tamano: Literal["pareja", "seis", "doce"]
    ingredientes: list[int] = Field(min_length=3)


# ====================== FUNCIONES DE APOYO ======================

# Busca un producto por su id en la lista leída del CSV; si no existe responde 404
def buscar(productos, producto_id: int):
    for producto in productos:
        if producto["id"] == producto_id:
            return producto
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"El producto {producto_id} no existe")


# Arma el renglón que se guarda en ventas.csv
def linea_de(producto, cantidad, descuento=0):
    return {
        "id_producto": producto["id"],
        "producto": producto["nombre"],
        "categoria": producto["categoria"],
        "cantidad": cantidad,
        "precio_unitario": round(producto["precio"] * (1 - descuento), 2),
        "costo_unitario": producto["costo"],
    }


# Cobra: descuenta el stock, reescribe productos.csv y registra la venta en ventas.csv
# productos = lista completa leída del CSV; items = lista de (producto, cantidad) tomados de esa lista
# armado = precio del servicio de armado (solo tablas). Se llama dentro de `async with lock`
def cobrar(productos, items, concepto, armado=None, descuento=0):
    try:
        # Primero se revisa todo el stock para no vender solo la mitad de una tabla
        for producto, cantidad in items:
            if producto["cantidad"] < cantidad:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"No hay stock suficiente de {producto['nombre']} "
                    f"(se necesitan {cantidad}, quedan {producto['cantidad']})",
                )

        lineas = []
        for producto, cantidad in items:
            producto["cantidad"] -= cantidad
            lineas.append(linea_de(producto, cantidad, descuento))
        if armado:
            lineas.append({
                "id_producto": 0, "producto": "Servicio de armado", "categoria": "servicio",
                "cantidad": 1, "precio_unitario": armado, "costo_unitario": armado * COSTO_ARMADO,
            })

        id_venta = registrar_venta(lineas, concepto)
        escribir_productos(productos)
        total = sum(l["cantidad"] * l["precio_unitario"] for l in lineas)
        return {
            "mensaje": "Compra realizada",
            "id_venta": id_venta,
            "concepto": concepto,
            "total": round(total, 2),
            "detalle": [
                {"producto": l["producto"], "cantidad": l["cantidad"],
                 "subtotal": round(l["cantidad"] * l["precio_unitario"], 2)}
                for l in lineas
            ],
        }
    except HTTPException:
        raise
    except Exception as error:
        # Cualquier error inesperado (por ejemplo, un CSV abierto en Excel) es un 500
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Error interno: {str(error)}")


# Valida los ingredientes de una tabla y calcula porciones y precio (no cambia nada en los CSV)
def armar_tabla(productos, tamano, ids):
    config = TAMANOS[tamano]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, "Hay ingredientes repetidos")
    if len(ids) > config["max_ingredientes"]:
        raise HTTPException(
            400, f"La {config['nombre'].lower()} lleva máximo {config['max_ingredientes']} ingredientes distintos")

    elegidos = [buscar(productos, i) for i in ids]
    for producto in elegidos:
        if producto["categoria"] not in PESO_CATEGORIA:
            raise HTTPException(
                400, f"{producto['nombre']} no va dentro de la tabla (los vinos y canastas se venden aparte)")

    # Para que la tabla quede equilibrada necesita las tres categorías
    categorias = [p["categoria"] for p in elegidos]
    for categoria, etiqueta in (("carne", "una carne fría"), ("queso", "un queso"), ("acompanamiento", "un acompañamiento")):
        if categoria not in categorias:
            raise HTTPException(400, f"La tabla necesita al menos {etiqueta}")

    porciones = repartir_porciones(config["porciones"], categorias)
    items = list(zip(elegidos, porciones))
    subtotal = sum(p["precio"] * n for p, n in items)
    return items, config, round(subtotal + config["armado"], 2)


# Convierte una tabla armada en el diccionario que se muestra al cliente
def describir_tabla(items, config, precio):
    return {
        "tamano_personas": config["personas"],
        "porciones_totales": config["porciones"],
        "ingredientes": [
            {"id": p["id"], "nombre": p["nombre"], "porciones": n, "subtotal": round(p["precio"] * n, 2)}
            for p, n in items
        ],
        "servicio_de_armado": config["armado"],
        "precio": precio,
        "hay_stock": all(p["cantidad"] >= n for p, n in items),
    }


# Precio de un maridaje con el descuento aplicado
def precio_maridaje(productos, maridaje):
    total = sum(
        linea_de(buscar(productos, i), n, DESCUENTO_MARIDAJE)["precio_unitario"] * n
        for i, n in maridaje["productos"].items()
    )
    return round(total, 2)


# ====================== ENDPOINTS: PRODUCTOS (CRUD en productos.csv) ======================

@app.get("/")
async def inicio():
    return {"tienda": NOMBRE_TIENDA, "lema": LEMA, "productos": len(leer_productos()), "tienda_web": "/tienda/"}


# Lista el catálogo leyendo productos.csv (opcional: ?categoria=vino)
@app.get("/productos")
async def get_productos(categoria: str | None = None):
    await asyncio.sleep(LATENCIA)
    productos = leer_productos()
    if categoria:
        return [p for p in productos if p["categoria"] == categoria]
    return productos


@app.get("/productos/{producto_id}")
async def get_producto(producto_id: int):
    return buscar(leer_productos(), producto_id)


# Registra un producto nuevo agregando una fila a productos.csv; responde 201 (Created)
@app.post("/productos", status_code=status.HTTP_201_CREATED)
async def agregar_producto(producto: ProductoNuevo):
    async with lock:
        await asyncio.sleep(LATENCIA)
        productos = leer_productos()
        nuevo = {"id": siguiente_id(productos), **producto.model_dump()}
        nuevo = {campo: nuevo[campo] for campo in CAMPOS_PRODUCTOS}
        productos.append(nuevo)
        escribir_productos(productos)
        return nuevo


# Compra de un producto suelto: POST /productos/3?cantidad=2
# Valida el stock, lo descuenta en productos.csv y registra la venta en ventas.csv
@app.post("/productos/{producto_id}")
async def comprar_producto(producto_id: int, cantidad: int = Query(1, ge=1, le=100)):
    async with lock:  # Punto de control: solo una compra a la vez
        productos = leer_productos()
        producto = buscar(productos, producto_id)
        await asyncio.sleep(LATENCIA)
        return cobrar(productos, [(producto, cantidad)], f"Compra: {producto['nombre']}")


# Elimina un producto: reescribe productos.csv sin ese registro (el historial en ventas.csv se conserva)
@app.delete("/productos/{producto_id}")
async def eliminar_producto(producto_id: int):
    async with lock:
        productos = leer_productos()
        producto = buscar(productos, producto_id)
        await asyncio.sleep(LATENCIA)
        escribir_productos([p for p in productos if p["id"] != producto_id])
        return {"mensaje": "Producto eliminado", "producto": producto["nombre"]}


# Surtir: suma producto al inventario cuando llega mercancía
@app.post("/productos/{producto_id}/surtir")
async def surtir_producto(producto_id: int, cantidad: int = Query(..., ge=1, le=1000)):
    async with lock:
        productos = leer_productos()
        producto = buscar(productos, producto_id)
        producto["cantidad"] += cantidad
        escribir_productos(productos)
        return {"mensaje": "Producto surtido", "producto": producto["nombre"], "cantidad_actual": producto["cantidad"]}


# Merma: producto caducado, dañado o perdido; sale del inventario y cuenta como pérdida
@app.post("/productos/{producto_id}/merma")
async def registrar_merma(producto_id: int, merma: Merma):
    async with lock:
        productos = leer_productos()
        producto = buscar(productos, producto_id)
        if producto["cantidad"] < merma.cantidad:
            raise HTTPException(400, f"Solo quedan {producto['cantidad']} de {producto['nombre']}")
        producto["cantidad"] -= merma.cantidad
        registrar_venta([linea_de(producto, merma.cantidad)], f"Merma: {merma.motivo}", tipo="merma")
        escribir_productos(productos)
        return {"mensaje": "Merma registrada", "producto": producto["nombre"],
                "perdida": round(merma.cantidad * producto["costo"], 2)}


# ====================== ENDPOINTS: TABLAS ======================

# Las tablas que la tienda ya tiene armadas (si falta un ingrediente porque se eliminó, avisa el motivo)
@app.get("/tablas")
async def get_tablas():
    productos = leer_productos()
    respuesta = []
    for codigo, tabla in TABLAS_DEFAULT.items():
        try:
            items, config, precio = armar_tabla(productos, tabla["tamano"], tabla["ingredientes"])
            respuesta.append({"codigo": codigo, "nombre": tabla["nombre"], **describir_tabla(items, config, precio)})
        except HTTPException as error:
            respuesta.append({"codigo": codigo, "nombre": tabla["nombre"], "motivo": error.detail})
    return respuesta


# Muestra cómo quedaría la tabla del cliente y cuánto cuesta, sin comprarla
@app.post("/tablas/personalizada/cotizar")
async def cotizar_tabla(tabla: TablaPersonalizada):
    items, config, precio = armar_tabla(leer_productos(), tabla.tamano, tabla.ingredientes)
    return describir_tabla(items, config, precio)


@app.post("/tablas/personalizada")
async def comprar_tabla_personalizada(tabla: TablaPersonalizada):
    async with lock:
        productos = leer_productos()
        items, config, precio = armar_tabla(productos, tabla.tamano, tabla.ingredientes)
        await asyncio.sleep(LATENCIA)
        return cobrar(productos, items, f"Tabla personalizada para {config['personas']}", armado=config["armado"])


# Compra una de las tablas por defecto: pareja, seis o doce
@app.post("/tablas/{codigo}/comprar")
async def comprar_tabla(codigo: Literal["pareja", "seis", "doce"]):
    async with lock:
        productos = leer_productos()
        tabla = TABLAS_DEFAULT[codigo]
        items, config, precio = armar_tabla(productos, tabla["tamano"], tabla["ingredientes"])
        await asyncio.sleep(LATENCIA)
        return cobrar(productos, items, tabla["nombre"], armado=config["armado"])


# ====================== ENDPOINTS: MARIDAJES ======================

@app.get("/maridajes")
async def get_maridajes():
    productos = leer_productos()
    respuesta = []
    for m in MARIDAJES:
        datos = {"id": m["id"], "nombre": m["nombre"], "tabla_ideal": TABLAS_DEFAULT[m["tabla_ideal"]]["nombre"],
                 "por_que": m["por_que"]}
        try:
            datos["contenido"] = [{"producto": buscar(productos, i)["nombre"], "cantidad": n} for i, n in m["productos"].items()]
            datos["precio"] = precio_maridaje(productos, m)
        except HTTPException as error:
            datos["motivo"] = error.detail
        respuesta.append(datos)
    return respuesta


@app.post("/maridajes/{maridaje_id}/comprar")
async def comprar_maridaje(maridaje_id: int):
    async with lock:
        productos = leer_productos()
        for m in MARIDAJES:
            if m["id"] == maridaje_id:
                items = [(buscar(productos, i), n) for i, n in m["productos"].items()]
                await asyncio.sleep(LATENCIA)
                respuesta = cobrar(productos, items, f"Maridaje: {m['nombre']}", descuento=DESCUENTO_MARIDAJE)
                respuesta["descuento"] = f"{int(DESCUENTO_MARIDAJE * 100)} % por comprar el maridaje completo"
                return respuesta
        raise HTTPException(404, "Ese maridaje no existe")


# ====================== ENDPOINTS: ANALÍTICOS CON PANDAS ======================

# KPIs: producto más comprado, ingresos totales, transacciones y ticket promedio
@app.get("/reportes/kpis")
async def reporte_kpis():
    return calcular_kpis()


# Serie: unidades e ingresos por producto (gráfica de barras)
@app.get("/reportes/ventas-por-producto")
async def reporte_por_producto():
    return calcular_ventas_por_producto()


# Serie: evolución de ingresos por fecha (gráfica de líneas)
@app.get("/reportes/ingresos-por-dia")
async def reporte_por_dia():
    return calcular_ingresos_por_dia()


# Serie: ingresos por categoría (gráfica de pastel)
@app.get("/reportes/categorias")
async def reporte_categorias():
    return calcular_por_categoria()


@app.get("/reportes/perdidas")
async def reporte_perdidas():
    return calcular_perdidas_por_producto()


# Qué productos hay que surtir y cuánto pedir
@app.get("/reportes/surtir")
async def reporte_surtir():
    return calcular_surtir()


# ====================== PÁGINA WEB ======================

# Sirve la carpeta frontend en http://127.0.0.1:8000/tienda/ (también se puede abrir frontend/index.html directo)
app.mount("/tienda", StaticFiles(directory=os.path.join(CARPETA, "frontend"), html=True), name="tienda")
