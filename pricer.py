import json
import sys
import requests
from datetime import datetime
from db_connection import get_connection


def obtener_precios_mexico(connection, ambiente="sandbox"):
    """Obtiene los 6 precios base de México por id_pais y ambiente"""
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
                pr.cantidad_precio,
                pr.id_pertenencia,
                p.nombre as producto_nombre,
                p.cantidad,
                pr.price_id as stripe_price_id
            FROM precio pr
            INNER JOIN pertenencia pe ON pr.id_pertenencia = pe.id
            INNER JOIN producto p ON pe.id_producto = p.id
            WHERE pr.id_pais = %s AND pr.nombre LIKE %s
            ORDER BY p.id
        """
        cursor.execute(query_precios, (pais_id_mexico, f'%{ambiente}%'))
        precios = cursor.fetchall()
        cursor.close()
        
        if len(precios) != 6:
            print(f"⚠️  Se encontraron {len(precios)} precios (se esperaban 6)")
            return None
        
        return precios
    except Exception as e:
        print(f"❌ Error al obtener precios de México: {e}")
        return None


def obtener_pais_info(connection, moneda_tic):
    """Obtiene la información del país por su código ISO"""
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM pais WHERE moneda_tic = %s"
        cursor.execute(query, (moneda_tic.upper(),))
        pais = cursor.fetchone()
        cursor.close()
        
        if not pais:
            print(f"❌ País con moneda {moneda_tic} no encontrado")
            return None
        
        return pais
    except Exception as e:
        print(f"❌ Error al obtener país: {e}")
        return None


def obtener_tipo_cambio(moneda_origen, moneda_destino):
    """Obtiene el tipo de cambio actual entre dos monedas"""
    try:
        print(f"\n💱 Obteniendo tipo de cambio {moneda_origen} -> {moneda_destino}...", end=" ")
        
        # Usar API gratuita sin clave de open.er-api.com
        url = f"https://open.er-api.com/v6/latest/{moneda_origen}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('result') == 'success' and data.get('rates'):
                tasa = data['rates'].get(moneda_destino)
                if tasa:
                    print(f"Tasa: {tasa:.4f}")
                    return tasa
        
        print(f"\n❌ Error al obtener tipo de cambio")
        print("   Verifica que tengas conexión a internet y que los códigos de moneda sean válidos.")
        return None
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return None


def redondear_inteligente(valor, precision=None):
    """Redondea un valor de forma proporcional según su magnitud"""
    import math
    
    # Si se especifica precisión manual, usarla
    if precision:
        resultado = math.ceil(valor / precision) * precision
        return resultado if resultado > 0 else precision
    
    # Determinar precisión automáticamente según el rango
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
    
    resultado = math.ceil(valor / precision) * precision
    return resultado if resultado > 0 else precision


def generar_json(moneda_tic, precios_finales):
    """Genera la estructura JSON con los precios finales"""
    json_data = {
        "moneda_tic": moneda_tic.upper(),
        "precios": []
    }
    
    for idx, precio in enumerate(precios_finales, 1):
        json_data["precios"].append({
            "numero_producto": idx,
            "cantidad_precio": precio['cantidad_precio'],
            "monto": float(precio['monto_final'])  # Garantizar que siempre sea float
        })
    
    return json_data


def guardar_json(json_data, nombre_archivo="plantilla.json"):
    """Guarda el JSON en un archivo"""
    try:
        with open(nombre_archivo, 'w') as f:
            json.dump(json_data, f, indent=2)
        print(f"\n✅ JSON guardado en: {nombre_archivo}")
        return True
    except Exception as e:
        print(f"❌ Error al guardar JSON: {e}")
        return False


def main():
    """Flujo principal interactivo"""
    print("\n" + "="*80)
    print("💰 GENERADOR DE PRECIOS POR PAÍS")
    print("="*80 + "\n")
    
    # Conectar a BD
    db = get_connection()
    if not db or not db.is_connected():
        print("❌ No se pudo conectar a la base de datos")
        return
    
    # 0. Preguntar ambiente
    print("📌 Selecciona el ambiente:")
    print("   1. sandbox")
    print("   2. production")
    while True:
        choice = input("\n   Ingresa tu opción (1 o 2): ").strip()
        if choice == "1":
            ambiente = "sandbox"
            break
        elif choice == "2":
            ambiente = "production"
            break
        else:
            print("   ❌ Ingresa 1 o 2\n")
    
    print(f"   ✅ Ambiente seleccionado: {ambiente}\n")
    
    # 1. Pedir código de país
    while True:
        moneda_tic = input("📍 Ingresa el código de moneda (ej: COP, ARS, BRL): ").strip().upper()
        
        # Validar que existe en la BD
        pais = obtener_pais_info(db, moneda_tic)
        if pais:
            print(f"   ✅ País encontrado: {pais['nombre']} ({pais['simbolo']})")
            break
        else:
            print(f"   ❌ Intenta de nuevo\n")
    
    # 2. Obtener precios base de México
    print(f"\n📦 Obteniendo precios base de México ({ambiente})...")
    precios_mexico = obtener_precios_mexico(db, ambiente)
    if not precios_mexico:
        db.close()
        return
    
    # Mostrar precios base de México para verificación
    print(f"\n✅ Precios base de México ({ambiente}):")
    print("   " + "-"*60)
    for idx, precio_mx in enumerate(precios_mexico, 1):
        print(f"   Producto {idx}: {precio_mx['producto_nombre']}")
        print(f"      Cantidad: {precio_mx['cantidad_precio']} imágenes")
        print(f"      Precio: ${precio_mx['cantidad_precio']:.2f} MXN")
        print(f"      ID Stripe: {precio_mx['stripe_price_id']}")
    print("   " + "-"*60 + "\n")
    
    # 3. Obtener tipo de cambio
    tasa_cambio = obtener_tipo_cambio("MXN", moneda_tic)
    if not tasa_cambio:
        print("\n⚠️  No se pudo obtener el tipo de cambio automáticamente")
        while True:
            try:
                tasa_cambio = float(input("   Ingresa manualmente el tipo de cambio (ej: 3.50): "))
                if tasa_cambio > 0:
                    print(f"   ✅ Tipo de cambio establecido en: {tasa_cambio:.4f}")
                    break
                else:
                    print("   ❌ Debe ser un número positivo\n")
            except ValueError:
                print("   ❌ Ingresa un número válido\n")
    
    # 4. Convertir precios
    print(f"\n💹 Convirtiendo precios con tasa {tasa_cambio:.4f}...\n")
    precios_propuestos = []
    
    for idx, precio_mx in enumerate(precios_mexico, 1):
        # Usar cantidad_precio como precio base en MXN
        precio_mxn = precio_mx['cantidad_precio']
        precio_convertido = precio_mxn * tasa_cambio
        precio_redondeado = redondear_inteligente(precio_convertido)  # Sin precisión fija, usa la inteligente
        
        precios_propuestos.append({
            'numero': idx,
            'producto': precio_mx['producto_nombre'],
            'cantidad_precio': precio_mx['cantidad_precio'],
            'precio_mxn': precio_mxn,
            'precio_convertido': precio_convertido,
            'precio_propuesto': precio_redondeado,
            'precio_final': precio_redondeado
        })
        
        print(f"   Producto {idx}: {precio_mx['producto_nombre']}")
        print(f"      Base MXN: ${precio_mxn:.2f}")
        print(f"      Convertido: {pais['simbolo']}{precio_convertido:.2f}")
        print(f"      Propuesto (redondeado): {pais['simbolo']}{precio_redondeado:.0f}\n")
    
    # 5. Preguntar si modificar precios
    print("\n" + "-"*80)
    print("✏️  Ahora puedes ajustar cada precio manualmente\n")
    
    precios_finales = []
    for precio in precios_propuestos:
        while True:
            respuesta = input(
                f"   Producto {precio['numero']} ({precio['producto']}): "
                f"Propuesto: {pais['simbolo']}{precio['precio_propuesto']:.0f}\n"
                f"   ¿Deseas modificarlo? (s/n): "
            ).strip().lower()
            
            if respuesta == 's':
                while True:
                    try:
                        nuevo_precio = float(input(f"   Ingresa el nuevo precio: "))
                        if nuevo_precio > 0:
                            precio['precio_final'] = nuevo_precio
                            print(f"   ✅ Precio actualizado a: {pais['simbolo']}{nuevo_precio:.2f}\n")
                            break
                        else:
                            print("   ❌ Debe ser un número positivo. Intenta de nuevo.\n")
                    except ValueError:
                        print("   ❌ Ingresa un número válido.\n")
                break
            elif respuesta == 'n':
                print(f"   ✅ Usando precio propuesto: {pais['simbolo']}{precio['precio_propuesto']:.0f}\n")
                break
            else:
                print("   ❌ Ingresa 's' o 'n'\n")
        
        precios_finales.append({
            'numero_producto': precio['numero'],
            'cantidad_precio': precio['cantidad_precio'],
            'monto_final': precio['precio_final']
        })
    
    # 6. Generar JSON
    json_data = generar_json(moneda_tic, precios_finales)
    
    # Mostrar resumen
    print("\n" + "="*80)
    print("📋 RESUMEN DE PRECIOS")
    print("="*80)
    print(f"País: {pais['nombre']} ({pais['simbolo']})")
    print(f"Moneda: {pais['moneda']} ({moneda_tic})\n")
    
    for precio in precios_finales:
        print(f"   Producto {precio['numero_producto']}: {pais['simbolo']}{precio['monto_final']:.0f}")
    
    print(f"\n{'='*80}\n")
    
    # 7. Guardar JSON
    if guardar_json(json_data, "plantilla.json"):
        print("\n✅ Listo para ejecutar: python crear_precios_pais.py plantilla.json sandbox")
    
    db.close()


if __name__ == '__main__':
    main()
