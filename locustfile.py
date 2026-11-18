### Autora: Laura Leal; Pruebas de carga de "Curado & Cava" con Locust
import random

# HttpUser es el usuario virtual, task marca lo que hace, between es la pausa entre acciones
from locust import HttpUser, task, between


class ClienteCuradoYCava(HttpUser):
    # Cada usuario espera entre 0.2 y 0.8 segundos entre una acción y otra
    wait_time = between(0.2, 0.8)

    # Peso 3: ver el catálogo (lo que más hace un cliente)
    @task(3)
    def ver_catalogo(self):
        self.client.get("/productos", name="/productos")

    # Peso 2: cotizar una tabla personalizada (no cambia el inventario)
    @task(2)
    def cotizar_tabla(self):
        cuerpo = {"tamano": "seis", "ingredientes": [1, 3, 9, 10, 21, 22]}
        self.client.post("/tablas/personalizada/cotizar", json=cuerpo, name="/tablas/personalizada/cotizar")

    # Peso 5: comprar un producto suelto (carne o queso al azar)
    @task(5)
    def comprar_producto(self):
        producto_id = random.randint(1, 14)
        # catch_response permite decidir qué respuesta cuenta como éxito
        with self.client.post(f"/productos/{producto_id}", name="/productos/[id] (comprar)", catch_response=True) as respuesta:
            # 200 = compra hecha; 400 = ya no hay stock (comportamiento esperado de la API)
            if respuesta.status_code in (200, 400):
                respuesta.success()
            else:
                respuesta.failure(f"Código inesperado: {respuesta.status_code}")

    # Peso 1: comprar el maridaje más sencillo
    @task(1)
    def comprar_maridaje(self):
        with self.client.post("/maridajes/1/comprar", name="/maridajes/[id]/comprar", catch_response=True) as respuesta:
            if respuesta.status_code in (200, 400):
                respuesta.success()
            else:
                respuesta.failure(f"Código inesperado: {respuesta.status_code}")

    # Peso 1: consultar qué hay que surtir (reporte con pandas)
    @task(1)
    def ver_reporte_surtir(self):
        self.client.get("/reportes/surtir", name="/reportes/surtir")
