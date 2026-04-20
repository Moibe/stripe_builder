import stripe
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os

from db_connection import get_connection
from utils import (
    obtener_paises_disponibles,
    obtener_pais_por_moneda,
    obtener_tipo_cambio,
    convertir_precio,
    redondear_inteligente,
    verificar_producto_stripe,
    crear_precio_stripe,
    generar_archivo_reporte,
)

# Cargar variables de entorno
load_dotenv()

app = FastAPI(
    title="Stripe Builder API",
    description="API para gestionar precios de Stripe para múltiples países",
    version="1.0.0",
)

# CORS - permitir acceso desde cualquier origen (ajustar en producción)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ──────────────────────────────────────────────────────────────────

NEGOCIOS_DISPONIBLES = {}

def cargar_negocios():
    """Detecta automáticamente los negocios configurados en .env"""
    negocios = {}
    prefix = "STRIPE_"
    for key, value in os.environ.items():
        if key.startswith(prefix) and key.endswith("_SECRET_KEY") and value and not value.startswith("COLOCA"):
            # STRIPE_{NEGOCIO}_{AMBIENTE}_SECRET_KEY
            parts = key[len(prefix):].rsplit("_SECRET_KEY", 1)[0]  # NEGOCIO_AMBIENTE
            # El ambiente es la última parte (SANDBOX o PROD)
            for env_suffix in ("_SANDBOX", "_PROD"):
                if parts.endswith(env_suffix):
                    negocio = parts[:len(parts) - len(env_suffix)].lower()
                    ambiente = env_suffix[1:].lower()  # sandbox o prod
                    if negocio not in negocios:
                        negocios[negocio] = {"ambientes": {}}
                    negocios[negocio]["ambientes"][ambiente] = {
                        "secret_key": value,
                        "publishable_key": os.getenv(f"{prefix}{negocio.upper()}_{ambiente.upper()}_PUBLISHABLE_KEY", ""),
                    }
                    break
    return negocios

# Cargar negocios al iniciar
NEGOCIOS_DISPONIBLES = cargar_negocios()


def init_stripe(business: str | None = None, environment: str = "prod"):
    """Inicializa Stripe con las claves del negocio y ambiente indicados"""
    if not business:
        business = os.getenv("STRIPE_DEFAULT_BUSINESS", "splashmix")
    business = business.lower()

    if business not in NEGOCIOS_DISPONIBLES:
        raise HTTPException(
            status_code=400,
            detail=f"Negocio '{business}' no encontrado. Disponibles: {list(NEGOCIOS_DISPONIBLES.keys())}"
        )

    ambientes = NEGOCIOS_DISPONIBLES[business]["ambientes"]
    if environment not in ambientes:
        raise HTTPException(
            status_code=400,
            detail=f"Negocio '{business}' no tiene ambiente '{environment}'. Disponibles: {list(ambientes.keys())}"
        )

    stripe.api_key = ambientes[environment]["secret_key"]


def get_db():
    """Obtiene conexión a BD, lanza excepción si falla"""
    conn = get_connection()
    if not conn or not conn.is_connected():
        raise HTTPException(status_code=500, detail="No se pudo conectar a la base de datos")
    return conn


# ── Modelos Pydantic ─────────────────────────────────────────────────────────

class ConversionRequest(BaseModel):
    precio_mxn: float
    moneda_destino: str


class CrearPrecioRequest(BaseModel):
    product_id: str
    monto: float
    moneda: str
    decs: int
    nickname: str | None = None


class CrearProductoRequest(BaseModel):
    nombre: str
    descripcion: str | None = None
    imagen_url: str | None = None
    precio_mxn: float | None = None
    nickname: str | None = None  # Etiqueta del precio (ej. "México - Nombre Producto")
    tipo: str = "puntual"  # "puntual" o "recurrente"
    periodo: str | None = None  # "diario", "semanal", "mensual", "anual" (solo si tipo=recurrente)
    tax_behavior: str = "unspecified"  # "inclusive", "exclusive", "unspecified"


class CrearPreciosPaisRequest(BaseModel):
    product_id: str
    precio_mxn: float
    nombre_producto: str
    moneda_destino: str
    monto_final: float


class CrearPreciosTodosRequest(BaseModel):
    product_id: str
    precio_mxn: float
    nombre_producto: str
    precios_por_pais: list[dict]  # [{moneda: str, monto: float}]


# ── Endpoints: Negocios ───────────────────────────────────────────────────────

@app.get("/businesses")
def listar_negocios():
    """Lista los negocios configurados y sus ambientes disponibles"""
    resultado = {}
    for negocio, info in NEGOCIOS_DISPONIBLES.items():
        resultado[negocio] = {
            "ambientes": list(info["ambientes"].keys()),
        }
    return {"default": os.getenv("STRIPE_DEFAULT_BUSINESS", "splashmix"), "negocios": resultado}


# ── Endpoints: Conexión ──────────────────────────────────────────────────────

@app.get("/connection/stripe")
def test_stripe_connection(environment: str = "prod", business: str | None = None):
    """Verifica la conexión a Stripe"""
    init_stripe(business, environment)
    try:
        account = stripe.Account.retrieve()
        return {
            "status": "conectado",
            "negocio": business or os.getenv("STRIPE_DEFAULT_BUSINESS", "splashmix"),
            "ambiente": environment,
            "email": account.get("email"),
            "business_name": account.get("business_profile", {}).get("name"),
            "country": account.get("country"),
            "account_id": account.get("id"),
        }
    except stripe.error.AuthenticationError:
        raise HTTPException(status_code=401, detail="Error de autenticación con Stripe")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/connection/db")
def test_db_connection():
    """Verifica la conexión a MariaDB"""
    try:
        conn = get_db()
        db_info = conn.get_server_info()
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE()")
        db_name = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {
            "status": "conectado",
            "version": db_info,
            "database": db_name,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoints: Países ────────────────────────────────────────────────────────

@app.get("/countries")
def listar_paises(incluir_mexico: bool = False):
    """Lista todos los países disponibles"""
    conn = get_db()
    try:
        paises = obtener_paises_disponibles(conn, excluir_mxn=not incluir_mexico)
        return {"total": len(paises), "paises": paises}
    finally:
        conn.close()


@app.get("/countries/{moneda_tic}")
def obtener_pais(moneda_tic: str):
    """Obtiene información de un país por su código de moneda"""
    conn = get_db()
    try:
        pais = obtener_pais_por_moneda(conn, moneda_tic.upper())
        if not pais:
            raise HTTPException(status_code=404, detail=f"País con moneda {moneda_tic} no encontrado")
        return pais
    finally:
        conn.close()


# ── Endpoints: Tipo de cambio ────────────────────────────────────────────────

@app.get("/exchange-rate/{moneda_origen}/{moneda_destino}")
def tipo_cambio(moneda_origen: str, moneda_destino: str):
    """Obtiene el tipo de cambio entre dos monedas"""
    tasa = obtener_tipo_cambio(moneda_origen.upper(), moneda_destino.upper())
    if not tasa:
        raise HTTPException(status_code=404, detail="No se pudo obtener el tipo de cambio")
    return {
        "moneda_origen": moneda_origen.upper(),
        "moneda_destino": moneda_destino.upper(),
        "tasa": tasa,
    }


# ── Endpoints: Conversión de precios ─────────────────────────────────────────

@app.post("/prices/convert")
def convertir(request: ConversionRequest):
    """Convierte un precio de MXN a otra moneda con redondeo inteligente"""
    resultado = convertir_precio(request.precio_mxn, request.moneda_destino.upper())
    if not resultado:
        raise HTTPException(status_code=404, detail="No se pudo obtener el tipo de cambio")
    return {
        "precio_mxn": request.precio_mxn,
        "moneda_destino": request.moneda_destino.upper(),
        **resultado,
    }


@app.post("/prices/convert-all")
def convertir_todos(precio_mxn: float):
    """Convierte un precio MXN a todas las monedas de los países disponibles"""
    conn = get_db()
    try:
        paises = obtener_paises_disponibles(conn)
        resultados = []

        for pais in paises:
            moneda = pais["moneda_tic"]
            conversion = convertir_precio(precio_mxn, moneda)
            if conversion:
                resultados.append({
                    "pais": pais["nombre"],
                    "moneda": moneda,
                    "decs": pais["decs"],
                    **conversion,
                })

        return {
            "precio_mxn": precio_mxn,
            "total_paises": len(resultados),
            "conversiones": resultados,
        }
    finally:
        conn.close()


# ── Endpoints: Productos ─────────────────────────────────────────────────────

@app.post("/products")
def crear_producto(request: CrearProductoRequest, environment: str = "prod", business: str | None = None):
    """Crea un nuevo producto en Stripe, opcionalmente con precio default en MXN"""
    init_stripe(business, environment)

    # Validaciones
    if request.tipo not in ("puntual", "recurrente"):
        raise HTTPException(status_code=400, detail="tipo debe ser 'puntual' o 'recurrente'")

    periodos_validos = {"diario": "day", "semanal": "week", "mensual": "month", "anual": "year"}
    if request.tipo == "recurrente" and request.precio_mxn is not None:
        if not request.periodo:
            raise HTTPException(status_code=400, detail="periodo es requerido para precios recurrentes")
        if request.periodo not in periodos_validos:
            raise HTTPException(status_code=400, detail=f"periodo debe ser: {', '.join(periodos_validos.keys())}")

    if request.tax_behavior not in ("inclusive", "exclusive", "unspecified"):
        raise HTTPException(status_code=400, detail="tax_behavior debe ser 'inclusive', 'exclusive' o 'unspecified'")

    try:
        # Crear producto
        product_params = {
            "name": request.nombre,
            "description": request.descripcion,
        }
        if request.imagen_url:
            product_params["images"] = [request.imagen_url]

        producto = stripe.Product.create(**product_params)

        resultado = {
            "product_id": producto.id,
            "nombre": producto.name,
            "descripcion": producto.description,
            "imagen": producto.images[0] if producto.images else None,
        }

        # Crear precio si se proporcionó
        if request.precio_mxn is not None:
            price_params = {
                "product": producto.id,
                "unit_amount": int(request.precio_mxn * 100),
                "currency": "mxn",
                "tax_behavior": request.tax_behavior,
                "nickname": request.nickname or f"México - {request.nombre}",
            }

            if request.tipo == "recurrente":
                price_params["recurring"] = {
                    "interval": periodos_validos[request.periodo],
                }

            precio = stripe.Price.create(**price_params)
            resultado["precio_mxn"] = {
                "price_id": precio.id,
                "monto": request.precio_mxn,
                "moneda": "MXN",
                "tipo": request.tipo,
                "periodo": request.periodo,
                "tax_behavior": request.tax_behavior,
            }

        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/products")
def listar_productos(
    environment: str = "prod",
    business: str | None = None,
    limit: int = 20,
    starting_after: str | None = None,
):
    """Lista los productos activos en Stripe con paginación.
    Usa `starting_after` (último product_id recibido) para obtener la siguiente página."""
    init_stripe(business, environment)
    try:
        params = {"limit": limit, "active": True}
        if starting_after:
            params["starting_after"] = starting_after

        products = stripe.Product.list(**params)
        resultado = []
        for product in products.data:
            precios = []
            last_price_id = None
            while True:
                price_params = {"product": product.id, "limit": 100}
                if last_price_id:
                    price_params["starting_after"] = last_price_id
                prices = stripe.Price.list(**price_params)
                for price in prices.data:
                    precios.append({
                        "price_id": price.id,
                        "monto": price.unit_amount / 100 if price.unit_amount else None,
                        "moneda": price.currency.upper(),
                        "tipo": price.type,
                    })
                if not prices.has_more:
                    break
                last_price_id = prices.data[-1].id
            resultado.append({
                "product_id": product.id,
                "nombre": product.name,
                "descripcion": product.description,
                "activo": product.active,
                "precios": precios,
            })
        return {
            "total": len(resultado),
            "has_more": products.has_more,
            "next_page": resultado[-1]["product_id"] if products.has_more and resultado else None,
            "productos": resultado,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/products/{product_id}")
def verificar_producto(product_id: str, environment: str = "prod", business: str | None = None):
    """Verifica un producto en Stripe y retorna sus precios en MXN"""
    init_stripe(business, environment)
    info = verificar_producto_stripe(product_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Producto {product_id} no encontrado")
    return info


@app.get("/products/{product_id}/prices")
def listar_precios_producto(product_id: str, environment: str = "prod", currency: str | None = None, business: str | None = None):
    """Lista todos los precios de un producto, opcionalmente filtrados por moneda"""
    init_stripe(business, environment)
    try:
        params = {"product": product_id, "limit": 100}
        if currency:
            params["currency"] = currency.lower()

        precios = stripe.Price.list(**params)
        resultado = []
        for p in precios.data:
            resultado.append({
                "price_id": p.id,
                "monto": p.unit_amount / 100 if p.unit_amount else None,
                "moneda": p.currency.upper(),
                "nickname": p.nickname,
                "activo": p.active,
            })
        return {"product_id": product_id, "total": len(resultado), "precios": resultado}
    except stripe.error.InvalidRequestError:
        raise HTTPException(status_code=404, detail=f"Producto {product_id} no encontrado")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/products/{product_id}/prices/{price_id}")
def archivar_precio(product_id: str, price_id: str, environment: str = "prod", business: str | None = None):
    """Archiva (desactiva) un precio en Stripe. Los precios no se pueden eliminar, solo archivar."""
    init_stripe(business, environment)
    try:
        precio = stripe.Price.modify(price_id, active=False)
        return {
            "price_id": precio.id,
            "product_id": product_id,
            "activo": precio.active,
            "mensaje": "Precio archivado correctamente",
        }
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoints: Crear precios ─────────────────────────────────────────────────

@app.post("/prices/create")
def crear_precio(request: CrearPrecioRequest, environment: str = "prod", business: str | None = None):
    """Crea un precio en Stripe para un producto y moneda específicos"""
    init_stripe(business, environment)
    price_id = crear_precio_stripe(
        request.product_id,
        request.monto,
        request.moneda,
        request.decs,
        request.nickname,
    )
    if not price_id:
        raise HTTPException(status_code=500, detail="No se pudo crear el precio en Stripe")
    return {
        "price_id": price_id,
        "product_id": request.product_id,
        "monto": request.monto,
        "moneda": request.moneda,
    }


@app.post("/prices/create-for-country")
def crear_precio_pais(request: CrearPreciosPaisRequest, environment: str = "prod", business: str | None = None):
    """Crea un precio para un producto en un país específico"""
    init_stripe(business, environment)
    conn = get_db()
    try:
        pais = obtener_pais_por_moneda(conn, request.moneda_destino.upper())
        if not pais:
            raise HTTPException(status_code=404, detail=f"País con moneda {request.moneda_destino} no encontrado")

        nickname = f"{pais['nombre']} - {request.nombre_producto}"
        price_id = crear_precio_stripe(
            request.product_id,
            request.monto_final,
            request.moneda_destino,
            pais["decs"],
            nickname,
        )
        if not price_id:
            raise HTTPException(status_code=500, detail="No se pudo crear el precio en Stripe")

        return {
            "price_id": price_id,
            "product_id": request.product_id,
            "pais": pais["nombre"],
            "moneda": request.moneda_destino.upper(),
            "monto": request.monto_final,
        }
    finally:
        conn.close()


@app.post("/prices/preview-all")
def previsualizar_precios_todos(request: CrearPreciosTodosRequest, business: str | None = None):
    """
    Previsualiza los precios que se crearían para cada país SIN escribir nada en Stripe.
    Útil para que el frontend muestre una tabla de confirmación antes de ejecutar.
    """
    conn = get_db()
    try:
        paises = obtener_paises_disponibles(conn)
        paises_dict = {p["moneda_tic"]: p for p in paises}

        preview = []
        errores = []

        for item in request.precios_por_pais:
            moneda = item["moneda"].upper()
            monto = item["monto"]
            pais = paises_dict.get(moneda)
            if not pais:
                errores.append({"moneda": moneda, "error": "País no encontrado"})
                continue
            preview.append({
                "pais": pais["nombre"],
                "moneda": moneda,
                "monto": monto,
                "nickname": f"{pais['nombre']} - {request.nombre_producto}",
            })

        return {
            "product_id": request.product_id,
            "nombre_producto": request.nombre_producto,
            "precio_mxn": request.precio_mxn,
            "total_a_crear": len(preview),
            "total_errores": len(errores),
            "preview": preview,
            "errores": errores,
        }
    finally:
        conn.close()


@app.post("/prices/create-all")
def crear_precios_todos(request: CrearPreciosTodosRequest, environment: str = "prod", business: str | None = None):
    """
    Crea precios para un producto en múltiples países de una sola vez.
    Recibe una lista de {moneda, monto} ya confirmados por el usuario.
    """
    init_stripe(business, environment)
    conn = get_db()
    try:
        paises = obtener_paises_disponibles(conn)
        paises_dict = {p["moneda_tic"]: p for p in paises}

        creados = []
        errores = []

        for item in request.precios_por_pais:
            moneda = item["moneda"].upper()
            monto = item["monto"]

            pais = paises_dict.get(moneda)
            if not pais:
                errores.append({"moneda": moneda, "error": "País no encontrado"})
                continue

            nickname = f"{pais['nombre']} - {request.nombre_producto}"
            price_id = crear_precio_stripe(
                request.product_id, monto, moneda, pais["decs"], nickname
            )

            if price_id:
                creados.append({
                    "pais": pais["nombre"],
                    "moneda": moneda,
                    "monto": monto,
                    "price_id": price_id,
                })
            else:
                errores.append({"moneda": moneda, "monto": monto, "error": "Stripe error"})

        # Generar archivo de reporte
        archivo = None
        if creados:
            archivo = generar_archivo_reporte(
                creados, request.nombre_producto, request.product_id, request.precio_mxn
            )

        return {
            "product_id": request.product_id,
            "nombre_producto": request.nombre_producto,
            "total_creados": len(creados),
            "total_errores": len(errores),
            "archivo_reporte": archivo,
            "creados": creados,
            "errores": errores,
        }
    finally:
        conn.close()
