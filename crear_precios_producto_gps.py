import stripe
import requests
from decimal import Decimal, ROUND_HALF_UP
from dotenv import load_dotenv
import os
from db_connection import get_connection
from datetime import datetime

# Cargar variables de entorno
load_dotenv()

# Configurar Stripe en production
stripe.api_key = os.getenv('STRIPE_PROD_SECRET_KEY')

# Constantes - Configurables por el usuario
PRODUCT_ID = "prod_TzbGHlbKHkeGiq"
PRECIO_MXN = 200
NOMBRE_PRODUCTO = "GPS SMS Location"
AMBIENTE = "prod"


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
    
    # Redondear al múltiplo más cercano de precision
    decimal_valor = Decimal(str(valor))
    decimal_precision = Decimal(str(precision))
    redondeado = decimal_valor.quantize(decimal_precision, rounding=ROUND_HALF_UP)
    return float(redondeado)


def obtener_tipo_cambio(moneda_origen, moneda_destino):
    """Obtiene el tipo de cambio actual entre dos monedas"""
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
    except Exception as e:
        print(f"   ❌ Error al obtener tipo de cambio: {e}")
        return None


def obtener_paises_disponibles(connection):
    """Obtiene todos los países disponibles en la BD"""
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT id, nombre, moneda_tic, decs 
            FROM pais 
            WHERE moneda_tic != 'MXN'
            ORDER BY nombre
        """
        cursor.execute(query)
        paises = cursor.fetchall()
        cursor.close()
        return paises
    except Exception as e:
        print(f"❌ Error al obtener países: {e}")
        return []


def crear_precio_stripe(product_id, monto, moneda, nombre_pais):
    """Crea un precio en Stripe para el producto"""
    try:
        # Calcular unit_amount según decimales de la moneda
        if moneda == 'CLP':
            multiplicador = 1  # CLP no tiene decimales
        else:
            multiplicador = 100  # USD, EUR, COP, PEN, MXN tienen 2 decimales
        
        unit_amount = int(monto * multiplicador)
        
        precio = stripe.Price.create(
            product=product_id,
            unit_amount=unit_amount,
            currency=moneda.lower(),
            nickname=f"{nombre_pais} - {NOMBRE_PRODUCTO}"
        )
        
        return precio['id']
    except Exception as e:
        print(f"   ❌ Error al crear precio en Stripe: {e}")
        return None


def main():
    print("=" * 90)
    print(f"🌍 CREAR PRECIOS POR PAÍS - PRODUCTO: {NOMBRE_PRODUCTO}")
    print("=" * 90)
    print(f"\n📌 Producto ID: {PRODUCT_ID}")
    print(f"💰 Precio base: ${PRECIO_MXN} MXN")
    print(f"🌐 Ambiente: PRODUCTION")
    
    # Conectar a BD
    try:
        connection = get_connection()
        paises = obtener_paises_disponibles(connection)
    except Exception as e:
        print(f"❌ Error de conexión a BD: {e}")
        return
    
    if not paises:
        print("❌ No hay países disponibles en la BD")
        return
    
    precios_creados = []
    
    print(f"\n📍 Países disponibles ({len(paises)}):")
    for i, pais in enumerate(paises, 1):
        print(f"   {i}. {pais['nombre']} ({pais['moneda_tic']})")
    
    print("\n" + "=" * 90)
    print("💰 CONVERSIÓN Y CREACIÓN DE PRECIOS")
    print("=" * 90)
    
    for pais in paises:
        nombre_pais = pais['nombre']
        moneda_destino = pais['moneda_tic']
        decs = pais['decs']
        
        print(f"\n🔄 {nombre_pais} ({moneda_destino}):")
        print(f"   Obteniendo tipo de cambio...", end=" ")
        
        # Obtener tipo de cambio
        tasa = obtener_tipo_cambio('MXN', moneda_destino)
        if not tasa:
            print(f"❌ No se pudo obtener el tipo de cambio")
            continue
        
        print(f"Tasa: {tasa:.4f}")
        
        # Convertir precio
        precio_convertido = PRECIO_MXN * tasa
        precio_redondeado = redondear_inteligente(precio_convertido)
        
        print(f"   Conversión: ${PRECIO_MXN} MXN × {tasa:.4f} = ${precio_convertido:.2f} {moneda_destino}")
        print(f"   Redondeado: ${precio_redondeado} {moneda_destino}")
        
        # Si hay redondeo, preguntar al usuario
        if abs(precio_convertido - precio_redondeado) > 0.01:
            print(f"   ⚠️  HAY DIFERENCIA POR REDONDEO: {abs(precio_convertido - precio_redondeado):.2f}")
            
            while True:
                respuesta = input(f"   ¿Usar ${precio_redondeado} {moneda_destino}? (s/n o ingresa otro valor): ").strip()
                
                if respuesta.lower() == 's':
                    precio_final = precio_redondeado
                    break
                elif respuesta.lower() == 'n':
                    try:
                        precio_final = float(input(f"   Ingresa el precio final en {moneda_destino}: "))
                        break
                    except ValueError:
                        print(f"   ❌ Valor inválido, intenta de nuevo")
                        continue
                else:
                    try:
                        precio_final = float(respuesta)
                        break
                    except ValueError:
                        print(f"   ❌ Valor inválido, intenta de nuevo")
                        continue
        else:
            precio_final = precio_redondeado
            print(f"   ✅ Sin redondeo significativo")
        
        # Crear precio en Stripe
        print(f"   Creando precio en Stripe...", end=" ")
        price_id = crear_precio_stripe(PRODUCT_ID, precio_final, moneda_destino, nombre_pais)
        
        if price_id:
            print(f"✅")
            print(f"   Price ID: {price_id}")
            precios_creados.append({
                'pais': nombre_pais,
                'moneda': moneda_destino,
                'monto': precio_final,
                'price_id': price_id
            })
        else:
            print(f"❌")
    
    # Generar archivo TXT
    if precios_creados:
        # Sanitizar nombre del producto para el archivo
        nombre_archivo = NOMBRE_PRODUCTO.replace(" ", "_").lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archivo_salida = f"precios_{nombre_archivo}_{timestamp}.txt"
        
        print("\n" + "=" * 90)
        print(f"📄 GENERANDO ARCHIVO: {archivo_salida}")
        print("=" * 90)
        
        with open(archivo_salida, 'w', encoding='utf-8') as f:
            f.write(f"PRECIOS CREADOS - {NOMBRE_PRODUCTO.upper()}\n")
            f.write("=" * 70 + "\n")
            f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Producto: {NOMBRE_PRODUCTO}\n")
            f.write(f"Product ID: {PRODUCT_ID}\n")
            f.write(f"Precio base: ${PRECIO_MXN} MXN\n")
            f.write(f"Ambiente: PRODUCTION\n")
            f.write("=" * 70 + "\n\n")
            
            for precio in precios_creados:
                f.write(f"{precio['pais']} ({precio['moneda']}): ${precio['monto']} → {precio['price_id']}\n")
        
        print(f"\n✅ Archivo creado: {archivo_salida}")
        print("\n📋 RESUMEN:")
        print(f"   Total de precios creados: {len(precios_creados)}")
        for precio in precios_creados:
            print(f"   {precio['pais']:25} ${precio['monto']:8.2f} {precio['moneda']} → {precio['price_id']}")
    else:
        print("\n❌ No se crearon precios")
    
    # Cerrar conexión
    try:
        connection.close()
    except:
        pass


if __name__ == "__main__":
    main()
