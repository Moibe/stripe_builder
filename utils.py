import stripe
import requests
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime


def normalizar_ambiente(ambiente):
    """Convierte 'prod' a 'production' y 'sandbox' se mantiene igual"""
    return 'production' if ambiente == 'prod' else ambiente


def redondear_inteligente(valor):
    """Redondea de forma inteligente según la magnitud del valor"""
    valor_abs = abs(valor)

    if valor_abs < 10:
        precision = 1
    elif valor_abs < 100:
        precision = 5
    elif valor_abs < 1000:
        precision = 10
    elif valor_abs < 10000:
        precision = 50
    else:
        precision = 100

    decimal_valor = Decimal(str(valor))
    decimal_precision = Decimal(str(precision))
    redondeado = decimal_valor.quantize(decimal_precision, rounding=ROUND_HALF_UP)
    return float(redondeado)


def obtener_tipo_cambio(moneda_origen, moneda_destino):
    """Obtiene el tipo de cambio actual entre dos monedas usando open.er-api.com"""
    try:
        url = f"https://open.er-api.com/v6/latest/{moneda_origen}"
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('result') == 'success' and data.get('rates'):
                tasa = data['rates'].get(moneda_destino)
                if tasa:
                    return tasa
        return None
    except Exception:
        return None


def obtener_paises_disponibles(connection, excluir_mxn=True):
    """Obtiene todos los países disponibles en la BD"""
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT id, nombre, moneda_tic, decs FROM pais"
        if excluir_mxn:
            query += " WHERE moneda_tic != 'MXN'"
        query += " ORDER BY nombre"
        cursor.execute(query)
        paises = cursor.fetchall()
        cursor.close()
        return paises
    except Exception:
        return []


def obtener_pais_por_moneda(connection, moneda_tic):
    """Obtiene los datos del país por su código de moneda ISO"""
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM pais WHERE moneda_tic = %s"
        cursor.execute(query, (moneda_tic,))
        pais = cursor.fetchone()
        cursor.close()
        return pais
    except Exception:
        return None


def verificar_producto_stripe(product_id):
    """Verifica un producto en Stripe y retorna su info con precios en MXN"""
    try:
        producto = stripe.Product.retrieve(product_id)
        precios_mxn = stripe.Price.list(product=product_id, currency='mxn', limit=100)

        precios = []
        for p in precios_mxn.data:
            precios.append({
                'price_id': p['id'],
                'monto': p['unit_amount'] / 100,
                'moneda': p['currency'].upper()
            })

        return {
            'nombre': producto['name'],
            'product_id': producto['id'],
            'activo': producto['active'],
            'precios_mxn': precios
        }
    except stripe.error.InvalidRequestError:
        return None
    except Exception:
        return None


def crear_precio_stripe(product_id, monto, moneda, decs, nickname=None):
    """Crea un precio en Stripe para un producto dado"""
    try:
        multiplicador = 10 ** decs
        unit_amount = int(monto * multiplicador)

        params = {
            'product': product_id,
            'unit_amount': unit_amount,
            'currency': moneda.lower(),
        }
        if nickname:
            params['nickname'] = nickname

        precio = stripe.Price.create(**params)
        return precio['id']
    except Exception:
        return None


def convertir_precio(precio_mxn, moneda_destino):
    """Convierte un precio de MXN a otra moneda y retorna info de conversión"""
    tasa = obtener_tipo_cambio('MXN', moneda_destino)
    if not tasa:
        return None

    precio_convertido = precio_mxn * tasa
    precio_redondeado = redondear_inteligente(precio_convertido)
    diferencia = abs(precio_convertido - precio_redondeado)

    return {
        'tasa': tasa,
        'precio_convertido': round(precio_convertido, 2),
        'precio_redondeado': precio_redondeado,
        'diferencia_redondeo': round(diferencia, 2),
        'requiere_confirmacion': diferencia > 0.01
    }


def generar_archivo_reporte(precios_creados, nombre_producto, product_id, precio_mxn):
    """Genera un archivo TXT con el reporte de precios creados"""
    nombre_archivo_base = nombre_producto.replace(" ", "_").lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo_salida = f"precios_{nombre_archivo_base}_{timestamp}.txt"

    with open(archivo_salida, 'w', encoding='utf-8') as f:
        f.write(f"PRECIOS CREADOS - {nombre_producto.upper()}\n")
        f.write("=" * 70 + "\n")
        f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Producto: {nombre_producto}\n")
        f.write(f"Product ID: {product_id}\n")
        f.write(f"Precio base: ${precio_mxn} MXN\n")
        f.write(f"Ambiente: PRODUCTION\n")
        f.write("=" * 70 + "\n\n")

        for precio in precios_creados:
            f.write(f"{precio['pais']} ({precio['moneda']}): ${precio['monto']} → {precio['price_id']}\n")

    return archivo_salida
