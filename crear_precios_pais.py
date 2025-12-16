import json
import sys
import stripe
from datetime import datetime
from db_connection import get_connection
from builder import StripeClient


def normalizar_ambiente(ambiente):
    """Convierte 'prod' a 'production' y 'sandbox' se mantiene igual"""
    return 'production' if ambiente == 'prod' else ambiente


def cargar_configuracion(ruta_json):
    """Carga la configuración desde un archivo JSON"""
    try:
        with open(ruta_json, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print(f"❌ Archivo no encontrado: {ruta_json}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Error al decodificar JSON en: {ruta_json}")
        sys.exit(1)


def obtener_pais_por_moneda(connection, moneda_tic):
    """Obtiene los datos del país por su código de moneda ISO"""
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM pais WHERE moneda_tic = %s"
        cursor.execute(query, (moneda_tic,))
        pais = cursor.fetchone()
        cursor.close()
        
        if not pais:
            print(f"❌ País con moneda {moneda_tic} no encontrado en la BD")
            return None
        
        return pais
    except Exception as e:
        print(f"❌ Error al buscar país: {e}")
        return None


def obtener_precios_mexico(connection, stripe_client):
    """Obtiene los 6 precios del conjunto de México con sus product_ids de Stripe"""
    try:
        cursor = connection.cursor(dictionary=True)
        
        # Obtener el país México por su moneda_tic
        query_pais = """
            SELECT id, nombre FROM pais WHERE moneda_tic = 'MXN'
        """
        cursor.execute(query_pais)
        pais_mexico = cursor.fetchone()
        
        if not pais_mexico:
            print("❌ País con moneda MXN (México) no encontrado")
            cursor.close()
            return None
        
        pais_id_mexico = pais_mexico['id']
        
        # Obtener los 6 precios de México directamente de la tabla precio
        # Filtrando por id_pais y ambiente (en el campo nombre)
        query_precios = """
            SELECT 
                pr.id as precio_id,
                pr.price_id as stripe_price_id,
                pr.cantidad_precio,
                p.id as producto_id,
                p.nombre as producto_nombre,
                p.cantidad,
                pe.id as pertenencia_id
            FROM precio pr
            INNER JOIN pertenencia pe ON pr.id_pertenencia = pe.id
            INNER JOIN producto p ON pe.id_producto = p.id
            WHERE pr.id_pais = %s AND pr.nombre LIKE %s
            ORDER BY p.id
        """
        cursor.execute(query_precios, (pais_id_mexico, f'%{stripe_client.environment}%'))
        precios = cursor.fetchall()
        cursor.close()
        
        if len(precios) != 6:
            print(f"⚠️  Se encontraron {len(precios)} precios (se esperaban 6)")
            return None
        
        # Para cada precio, obtener el product_id de Stripe
        precios_con_product = []
        for precio in precios:
            try:
                # Consultar el precio en Stripe
                stripe_price = stripe.Price.retrieve(precio['stripe_price_id'])
                precio['stripe_product_id'] = stripe_price.product
                precios_con_product.append(precio)
                print(f"   ✓ Producto {precio['producto_nombre']}: {stripe_price.product}")
            except Exception as e:
                print(f"   ❌ Error al obtener product_id para {precio['producto_nombre']}: {e}")
                return None
        
        return precios_con_product
    except Exception as e:
        print(f"❌ Error al obtener precios de México: {e}")
        return None


def crear_conjunto_pais(connection, pais_nombre):
    """Crea un nuevo conjunto para el país"""
    try:
        cursor = connection.cursor()
        
        # Obtener el siguiente ID
        query_max = "SELECT MAX(id) as max_id FROM conjunto"
        cursor.execute(query_max)
        result = cursor.fetchone()
        nuevo_id = (result[0] or 0) + 1
        
        query_insert = """
            INSERT INTO conjunto (id, sitio, nombre, created_at)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query_insert, (nuevo_id, pais_nombre, pais_nombre, datetime.now()))
        connection.commit()
        cursor.close()
        
        print(f"✅ Conjunto creado para {pais_nombre} (ID: {nuevo_id})")
        return nuevo_id
    except Exception as e:
        print(f"❌ Error al crear conjunto: {e}")
        connection.rollback()
        return None


def crear_pertenencias(connection, nuevo_conjunto_id, productos):
    """Crea las relaciones pertenencia entre productos y el nuevo conjunto"""
    try:
        cursor = connection.cursor()
        pertenencias = []
        
        # Obtener el siguiente ID de pertenencia
        query_max = "SELECT MAX(id) as max_id FROM pertenencia"
        cursor.execute(query_max)
        result = cursor.fetchone()
        siguiente_id = (result[0] or 0) + 1
        
        for producto in productos:
            query_insert = """
                INSERT INTO pertenencia (id, id_conjunto, id_producto, created_at)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query_insert, (siguiente_id, nuevo_conjunto_id, producto['producto_id'], datetime.now()))
            pertenencias.append({'id': siguiente_id, 'producto_id': producto['producto_id']})
            siguiente_id += 1
        
        connection.commit()
        cursor.close()
        
        print(f"✅ {len(pertenencias)} relaciones de pertenencia creadas")
        return pertenencias
    except Exception as e:
        print(f"❌ Error al crear pertenencias: {e}")
        connection.rollback()
        return None


def crear_precio_stripe(stripe_client, pais, producto, cantidad_precio, monto):
    """Crea un precio en Stripe"""
    try:
        # Convertir monto a centavos
        monto_centavos = int(monto * 100)
        
        nombre_precio = f"{pais['moneda_tic'].lower()}-splashmix-{cantidad_precio}-imagen-{stripe_client.environment}"
        
        precio = stripe.Price.create(
            product=producto['stripe_product_id'] if 'stripe_product_id' in producto else None,
            unit_amount=monto_centavos,
            currency=pais['moneda_tic'].lower(),
            metadata={
                'nombre': nombre_precio,
                'cantidad_precio': cantidad_precio,
                'pais': pais['nombre']
            }
        )
        
        return precio.id
    except Exception as e:
        print(f"❌ Error al crear precio en Stripe: {e}")
        return None


def insertar_precio_bd(connection, pertenencia_id, pais_id, price_id, cantidad_precio, 
                       ratio_imagen, nombre_precio, ambiente):
    """Inserta el precio en la tabla precio de la BD"""
    try:
        cursor = connection.cursor()
        
        # Obtener el siguiente ID
        query_max = "SELECT MAX(id) as max_id FROM precio"
        cursor.execute(query_max)
        result = cursor.fetchone()
        nuevo_id = (result[0] or 0) + 1
        
        query_insert = """
            INSERT INTO precio (id, nombre, id_pertenencia, id_pais, price_id, 
                              cantidad_precio, ratio_imagen, status, ambiente, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query_insert, (
            nuevo_id,
            nombre_precio,
            pertenencia_id,
            pais_id,
            price_id,
            cantidad_precio,
            ratio_imagen,
            'activo',
            ambiente,
            datetime.now()
        ))
        connection.commit()
        cursor.close()
        
        return True
    except Exception as e:
        print(f"❌ Error al insertar precio en BD: {e}")
        connection.rollback()
        return False


def procesar_pais(config_file, stripe_environment=None):
    """Procesa el archivo de configuración y crea los precios"""
    print("\n" + "="*80)
    print("🌍 CREAR PRECIOS PARA NUEVO PAÍS")
    print("="*80 + "\n")
    
    # Cargar configuración
    config = cargar_configuracion(config_file)
    moneda_tic = config.get('moneda_tic')
    precios = config.get('precios', [])
    
    if not moneda_tic or len(precios) != 6:
        print("❌ Configuración inválida. Se requiere moneda_tic y exactamente 6 precios")
        return
    
    # Conectar a Stripe
    stripe_client = StripeClient(stripe_environment)
    print(f"✅ Conectado a Stripe ({stripe_client.environment.upper()})\n")
    
    # Conectar a BD
    db = get_connection()
    if not db or not db.is_connected():
        print("❌ No se pudo conectar a la base de datos")
        return
    
    print("✅ Conectado a MariaDB\n")
    
    # Obtener info del país
    pais = obtener_pais_por_moneda(db, moneda_tic)
    if not pais:
        db.close()
        return
    
    print(f"📍 País: {pais['nombre']} ({moneda_tic})")
    print(f"   Moneda: {pais['moneda']}")
    print(f"   Símbolo: {pais['simbolo']}\n")
    
    # Obtener precios de México con product_ids
    print("📦 Obteniendo product_ids de Stripe para los 6 productos de México...")
    precios_mexico = obtener_precios_mexico(db, stripe_client)
    if not precios_mexico or len(precios_mexico) != 6:
        db.close()
        return
    
    print()  # Espacio en blanco
    
    # Crear nuevo conjunto
    nuevo_conjunto_id = crear_conjunto_pais(db, pais['nombre'])
    if not nuevo_conjunto_id:
        db.close()
        return
    
    # Crear pertenencias
    pertenencias = crear_pertenencias(db, nuevo_conjunto_id, precios_mexico)
    if not pertenencias:
        db.close()
        return
    
    print(f"\n💰 Creando {len(precios)} precios en Stripe...\n")
    
    # Procesar cada precio
    precios_creados = 0
    for idx, precio_config in enumerate(precios):
        num_producto = precio_config.get('numero_producto')
        cantidad_precio = precio_config.get('cantidad_precio')
        monto = precio_config.get('monto')
        
        # Validar
        if not num_producto or not cantidad_precio or not monto:
            print(f"⚠️  Precio {idx+1} incompleto. Se saltará.")
            continue
        
        # Obtener producto correspondiente de México
        if num_producto > len(precios_mexico):
            print(f"⚠️  Producto {num_producto} no existe. Se saltará.")
            continue
        
        precio_mexico = precios_mexico[num_producto - 1]
        pertenencia = pertenencias[num_producto - 1]
        
        # Crear nombre
        nombre_precio = f"{moneda_tic.lower()}-splashmix-{cantidad_precio}-imagen-{stripe_client.environment}"
        
        # Calcular ratio
        ratio_imagen = int(cantidad_precio / precio_mexico['cantidad'])
        
        # Crear precio en Stripe
        print(f"   Creando precio #{num_producto}: {monto} {pais['simbolo']} ({cantidad_precio} imágenes)...", end=" ")
        
        try:
            precio_stripe = stripe.Price.create(
                product=precio_mexico['stripe_product_id'],
                unit_amount=int(monto * 100),
                currency=pais['moneda_tic'].lower(),
                metadata={
                    'nombre': nombre_precio,
                    'cantidad_precio': cantidad_precio,
                    'pais': pais['nombre']
                }
            )
            
            price_id = precio_stripe.id
            
            # Insertar en BD con ambiente normalizado
            ambiente_normalizado = normalizar_ambiente(stripe_client.environment)
            if insertar_precio_bd(db, pertenencia['id'], pais['id'], price_id, 
                                 cantidad_precio, ratio_imagen, nombre_precio, ambiente_normalizado):
                print("✅")
                precios_creados += 1
            else:
                print("❌ (Error en BD)")
        
        except Exception as e:
            print(f"❌ ({str(e)})")
    
    print(f"\n{'='*80}")
    print(f"✅ Proceso completado: {precios_creados}/{len(precios)} precios creados exitosamente")
    print(f"{'='*80}\n")
    
    db.close()


def main():
    """Función principal"""
    if len(sys.argv) < 2:
        print("Uso: python crear_precios_pais.py <archivo_config.json> [ambiente]")
        print("Ejemplo: python crear_precios_pais.py plantilla.json sandbox")
        sys.exit(1)
    
    config_file = sys.argv[1]
    stripe_env = sys.argv[2] if len(sys.argv) > 2 else None
    
    procesar_pais(config_file, stripe_env)


if __name__ == '__main__':
    main()
