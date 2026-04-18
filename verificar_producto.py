import stripe
from dotenv import load_dotenv
import os

# Cargar variables de entorno
load_dotenv()

# Configurar Stripe en production
stripe.api_key = os.getenv('STRIPE_PROD_SECRET_KEY')

# Datos a verificar
PRODUCT_ID = "prod_TuGgeHxdbLvTb2"
PRICE_ID = "price_1SwS90IYi36CbmfWyRmmJUxN"
PRECIO_ESPERADO_MXN = 100  # en MXN

print("=" * 80)
print("🔍 VERIFICACIÓN DE PRODUCTO EN STRIPE (PRODUCTION)")
print("=" * 80)

try:
    # 1. Verificar que el producto existe
    print(f"\n1️⃣  Buscando producto: {PRODUCT_ID}...")
    producto = stripe.Product.retrieve(PRODUCT_ID)
    print(f"   ✅ Producto encontrado: {producto['name']}")
    print(f"   ID: {producto['id']}")
    
    # 2. Verificar que el price_id existe y pertenece a este producto
    print(f"\n2️⃣  Buscando price: {PRICE_ID}...")
    precio = stripe.Price.retrieve(PRICE_ID)
    print(f"   ✅ Price encontrado")
    print(f"   ID: {precio['id']}")
    print(f"   Moneda: {precio['currency'].upper()}")
    print(f"   Unit Amount: {precio['unit_amount']}")
    print(f"   Monto formateado: {precio['unit_amount'] / 100} {precio['currency'].upper()}")
    
    # 3. Verificar que el price pertenece al producto
    if precio['product'] == PRODUCT_ID:
        print(f"   ✅ El price pertenece al producto correcto")
    else:
        print(f"   ❌ El price NO pertenece al producto {PRODUCT_ID}")
        print(f"      Pertenece a: {precio['product']}")
    
    # 4. Verificar el monto en MXN
    print(f"\n3️⃣  Verificando monto en MXN...")
    monto_mxn = precio['unit_amount'] / 100  # Stripe almacena en centavos
    if abs(monto_mxn - PRECIO_ESPERADO_MXN) < 0.01:
        print(f"   ✅ Monto correcto: ${monto_mxn} MXN")
    else:
        print(f"   ❌ Monto incorrecto")
        print(f"      Esperado: ${PRECIO_ESPERADO_MXN} MXN")
        print(f"      Encontrado: ${monto_mxn} MXN")
    
    # 5. Resumen
    print("\n" + "=" * 80)
    print("📋 RESUMEN DE VERIFICACIÓN")
    print("=" * 80)
    print(f"Producto: {producto['name']} ({PRODUCT_ID})")
    print(f"Price ID: {PRICE_ID}")
    print(f"Moneda: {precio['currency'].upper()}")
    print(f"Monto: ${monto_mxn} {precio['currency'].upper()}")
    print(f"Estado: ✅ TODOS LOS DATOS SON CORRECTOS")
    print("=" * 80)

except stripe.error.InvalidRequestError as e:
    print(f"\n❌ Error: No se encontró el recurso")
    print(f"   Detalles: {e.user_message}")
    
except stripe.error.AuthenticationError as e:
    print(f"\n❌ Error de autenticación con Stripe")
    print(f"   Verifica que las claves en .env sean correctas")
    
except Exception as e:
    print(f"\n❌ Error inesperado: {e}")
