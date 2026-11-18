// Autora: Laura Leal; cliente de "Curado & Cava". Consume la API de FastAPI con fetch().

// Si se abre con doble clic (file://) usa la API en el puerto 8000; si se abre desde /tienda/ usa la misma dirección
const API = location.protocol === "file:" ? "http://127.0.0.1:8000" : "";

// Instancias de Chart.js (se guardan para destruirlas antes de volver a dibujar)
let graficaProductos = null;
let graficaCategorias = null;
let graficaFechas = null;

const COLORES = ["#5b1a2b", "#c9a24d", "#8a6a1f", "#a94b63", "#d9b97a", "#3a0f1b", "#b8860b", "#7a2a3f"];


// ---------- Utilidades ----------

// Muestra un mensaje arriba de la página (verde si salió bien, rojo si hubo error)
function mostrarMensaje(texto, esError) {
  const caja = document.getElementById("mensaje");
  caja.textContent = texto;
  caja.className = esError ? "error" : "ok";
  setTimeout(() => { caja.className = ""; }, 5000);
}

// Hace la petición, avisa si hubo error y regresa los datos (o null si falló)
async function pedir(ruta, opciones) {
  try {
    const respuesta = await fetch(API + ruta, opciones);
    const datos = await respuesta.json();
    if (!respuesta.ok) {
      // FastAPI manda el error en "detail" (texto en 400/404; lista en 422)
      const detalle = typeof datos.detail === "string" ? datos.detail : JSON.stringify(datos.detail);
      mostrarMensaje(detalle, true);
      return null;
    }
    return datos;
  } catch (error) {
    mostrarMensaje("No se pudo conectar con la API. ¿Está corriendo Uvicorn?", true);
    return null;
  }
}

function peso(n) { return "$" + Number(n).toLocaleString("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

function opcionesPost(cuerpo) {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) };
}

// Después de cualquier cambio se actualiza todo: catálogo, tablas, maridajes, KPIs y gráficas
async function refrescarTodo() {
  await Promise.all([cargarCatalogo(), cargarTablas(), cargarMaridajes(), cargarDashboard()]);
}

// Muestra el mensaje de una compra y actualiza la página
function compraRealizada(datos) {
  mostrarMensaje(`${datos.concepto}: ${peso(datos.total)} (venta #${datos.id_venta})`, false);
  refrescarTodo();
}


// ---------- Catálogo (CRUD) ----------

async function cargarCatalogo() {
  const productos = await pedir("/productos");
  if (!productos) return;
  document.getElementById("tabla-catalogo").innerHTML = productos.map(p => `
    <tr>
      <td>${p.nombre}</td><td>${p.categoria}</td><td>${peso(p.precio)}</td><td>${p.cantidad}</td>
      <td>
        <button onclick="comprarProducto(${p.id})">Comprar</button>
        <button class="eliminar" onclick="eliminarProducto(${p.id}, '${p.nombre.replace(/'/g, "\\'")}')">Eliminar</button>
      </td>
    </tr>`).join("");

  // Casillas del armador de tablas (solo carnes, quesos y acompañamientos); se conserva lo ya marcado
  const marcados = new Set([...document.querySelectorAll("#ingredientes input:checked")].map(c => c.value));
  const grupos = { carne: "Carnes frías", queso: "Quesos", acompanamiento: "Acompañamientos" };
  document.getElementById("ingredientes").innerHTML = Object.entries(grupos).map(([cat, titulo]) => `
    <div class="grupo"><strong>${titulo}</strong><br>` +
    productos.filter(p => p.categoria === cat).map(p =>
      `<label><input type="checkbox" value="${p.id}" ${marcados.has(String(p.id)) ? "checked" : ""}> ${p.nombre} (${peso(p.precio)})</label><br>`).join("") +
    `</div>`).join("");
}

async function comprarProducto(id) {
  const datos = await pedir(`/productos/${id}`, { method: "POST" });
  if (datos) compraRealizada(datos);
}

async function eliminarProducto(id, nombre) {
  if (!confirm(`¿Eliminar "${nombre}" del catálogo?`)) return;
  const datos = await pedir(`/productos/${id}`, { method: "DELETE" });
  if (datos) {
    mostrarMensaje(`${datos.producto}: eliminado del catálogo`, false);
    refrescarTodo();
  }
}

async function agregarProducto(evento) {
  evento.preventDefault();
  const cuerpo = {
    nombre: document.getElementById("nuevo-nombre").value,
    categoria: document.getElementById("nuevo-categoria").value,
    unidad: document.getElementById("nuevo-unidad").value || "pieza",
    precio: Number(document.getElementById("nuevo-precio").value),
    costo: Number(document.getElementById("nuevo-costo").value),
    cantidad: Number(document.getElementById("nuevo-cantidad").value),
    minimo: Number(document.getElementById("nuevo-minimo").value || 0),
  };
  const datos = await pedir("/productos", opcionesPost(cuerpo));
  if (datos) {
    mostrarMensaje(`${datos.nombre} agregado al catálogo`, false);
    document.getElementById("form-producto").reset();
    refrescarTodo();
  }
}


// ---------- Tablas y maridajes ----------

async function cargarTablas() {
  const tablas = await pedir("/tablas");
  if (!tablas) return;
  document.getElementById("lista-tablas").innerHTML = tablas.map(t => t.motivo ? `
    <div class="tarjeta"><h3>${t.nombre}</h3><p class="aviso">No disponible: ${t.motivo}</p></div>` : `
    <div class="tarjeta">
      <h3>${t.nombre}</h3>
      <p>Para ${t.tamano_personas} personas · ${t.porciones_totales} porciones</p>
      <p>${t.ingredientes.map(i => `${i.nombre} x${i.porciones}`).join(", ")}</p>
      <p class="precio">${peso(t.precio)} ${t.hay_stock ? "" : "(sin stock)"}</p>
      <button onclick="comprarTabla('${t.codigo}')">Comprar</button>
    </div>`).join("");
}

async function comprarTabla(codigo) {
  const datos = await pedir(`/tablas/${codigo}/comprar`, { method: "POST" });
  if (datos) compraRealizada(datos);
}

async function cargarMaridajes() {
  const maridajes = await pedir("/maridajes");
  if (!maridajes) return;
  document.getElementById("lista-maridajes").innerHTML = maridajes.map(m => m.motivo ? `
    <div class="tarjeta"><h3>${m.nombre}</h3><p class="aviso">No disponible: ${m.motivo}</p></div>` : `
    <div class="tarjeta">
      <h3>${m.nombre}</h3>
      <p><em>Ideal con: ${m.tabla_ideal}</em></p>
      <p>${m.contenido.map(c => `${c.producto} x${c.cantidad}`).join(", ")}</p>
      <p>${m.por_que}</p>
      <p class="precio">${peso(m.precio)}</p>
      <button onclick="comprarMaridaje(${m.id})">Comprar</button>
    </div>`).join("");
}

async function comprarMaridaje(id) {
  const datos = await pedir(`/maridajes/${id}/comprar`, { method: "POST" });
  if (datos) compraRealizada(datos);
}

// Lee el tamaño y los ingredientes marcados en la página
function tablaElegida() {
  const ingredientes = [...document.querySelectorAll("#ingredientes input:checked")].map(c => Number(c.value));
  return { tamano: document.getElementById("tamano").value, ingredientes };
}

async function cotizar() {
  const datos = await pedir("/tablas/personalizada/cotizar", opcionesPost(tablaElegida()));
  if (!datos) return;
  document.getElementById("cotizacion").textContent =
    datos.ingredientes.map(i => `${i.nombre}: ${i.porciones} porc. = ${peso(i.subtotal)}`).join("\n") +
    `\nServicio de armado: ${peso(datos.servicio_de_armado)}\nTOTAL: ${peso(datos.precio)}` +
    (datos.hay_stock ? "" : "\n(Falta stock de algún ingrediente)");
}

async function comprarPersonalizada() {
  const datos = await pedir("/tablas/personalizada", opcionesPost(tablaElegida()));
  if (datos) compraRealizada(datos);
}


// ---------- Dashboard (KPIs y gráficas con Chart.js) ----------

// Destruye la gráfica anterior (si existe) y dibuja una nueva en el canvas indicado
function dibujar(idCanvas, anterior, configuracion) {
  if (anterior) anterior.destroy();
  return new Chart(document.getElementById(idCanvas), configuracion);
}

function pintarKpis(k) {
  const estrella = k.producto_mas_comprado;
  document.getElementById("kpi-estrella").textContent = estrella ? estrella.nombre : "Sin ventas";
  document.getElementById("kpi-estrella-detalle").textContent = estrella ? `${estrella.unidades} unidades vendidas` : "";
  document.getElementById("kpi-ingresos").textContent = peso(k.ingresos_totales);
  document.getElementById("kpi-ingresos-detalle").textContent =
    k.producto_mayor_ingreso ? `Más ingresos: ${k.producto_mayor_ingreso.nombre}` : "";
  document.getElementById("kpi-transacciones").textContent = k.total_transacciones;
  document.getElementById("kpi-unidades").textContent = `${k.unidades_vendidas} unidades en total`;
  document.getElementById("kpi-ticket").textContent = peso(k.ticket_promedio);
}

async function cargarDashboard() {
  const [kpis, porProducto, porDia, porCategoria, surtir] = await Promise.all([
    pedir("/reportes/kpis"),
    pedir("/reportes/ventas-por-producto"),
    pedir("/reportes/ingresos-por-dia"),
    pedir("/reportes/categorias"),
    pedir("/reportes/surtir"),
  ]);

  if (kpis) pintarKpis(kpis);

  // Gráfica de barras: ingresos de los 8 productos que más venden
  if (porProducto) {
    const top = porProducto.slice(0, 8);
    graficaProductos = dibujar("grafica-productos", graficaProductos, {
      type: "bar",
      data: {
        labels: top.map(p => p.producto),
        datasets: [{ label: "Ingresos ($)", data: top.map(p => p.ingresos), backgroundColor: "#5b1a2b" }],
      },
      options: { indexAxis: "y", plugins: { legend: { display: false } } },
    });
  }

  // Gráfica de pastel: ingresos por categoría
  if (porCategoria) {
    graficaCategorias = dibujar("grafica-categorias", graficaCategorias, {
      type: "doughnut",
      data: {
        labels: porCategoria.map(c => c.categoria),
        datasets: [{ data: porCategoria.map(c => c.ingresos), backgroundColor: COLORES }],
      },
    });
  }

  // Gráfica de líneas: ingresos y utilidad por día
  if (porDia) {
    graficaFechas = dibujar("grafica-fechas", graficaFechas, {
      type: "line",
      data: {
        labels: porDia.map(d => d.dia),
        datasets: [
          { label: "Ingresos ($)", data: porDia.map(d => d.ingresos), borderColor: "#5b1a2b", backgroundColor: "rgba(91,26,43,0.12)", fill: true, tension: 0.3 },
          { label: "Utilidad ($)", data: porDia.map(d => d.utilidad), borderColor: "#c9a24d", tension: 0.3 },
        ],
      },
    });
  }

  // Tabla de productos por surtir
  if (surtir) {
    document.getElementById("surtir-resumen").textContent = surtir.productos_a_surtir.length
      ? `Inversión necesaria para surtir: ${peso(surtir.inversion_necesaria)}`
      : "Por ahora no hay productos urgentes por surtir.";
    document.getElementById("tabla-surtir").innerHTML = surtir.productos_a_surtir.map(p => `
      <tr><td>${p.nombre}</td><td>${p.cantidad}</td><td>${p.minimo}</td>
      <td>${p.dias_restantes === null ? "-" : p.dias_restantes}</td><td>${p.surtir}</td></tr>`).join("");
  }
}

refrescarTodo();
