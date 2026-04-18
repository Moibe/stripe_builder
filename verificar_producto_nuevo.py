import stripe
from dotenv import load_dotenv
import os

# Cargar variables de entorno
load_dotenv()

# Configurar Stripe en production
stripe.api_key = os.getenv('STRIPE_PROD_SECRET_KEY')

PRODUCT_ID = "prod_U4wmT5U2hLGQoM"

print("=" * 80)
print("🔍 VERIFICACIÓN DE PRODUCTO EN STRIPE (PRODUCTION)")
print("=" * 80)

try:
    # Obtener el producto
    print(f"\n1️⃣  Buscando producto: {PRODUCT_ID}...")
    producto = stripe.Product.retrieve(PRODUCT_ID)
    print(f"   ✅ Producto encontrado: {producto['name']}")
    
    # Obtener los precios asociados al producto
    print(f"\n2️⃣  Buscando precios en MXN para este producto...")
    precios = stripe.Price.list(product=PRODUCT_ID, currency='mxn', limit=100)
    
    if precios.data:
        print(f"   ✅ Se encontraron {len(precios.data)} precio(s) en MXN")
        for i, precio in enumerate(precios.data, 1):
            monto = precio['unit_amount'] / 100
            print(f"      {i}. {precio['id']}: ${monto} MXN")
    else:
        print(f"   ⚠️  No se encontraron precios en MXN para este producto")
        print(f"      Buscando todos los precios del producto...")
        todos_precios = stripe.Price.list(product=PRODUCT_ID, limit=100)
        if todos_precios.data:
            for i, precio in enumerate(todos_precios.data, 1):
                monto = precio['unit_amount'] / 100 if precio['unit_amount'] else 0
                print(f"      {i}. {precio['id']}: ${monto} {precio['currency'].upper()}")

except stripe.error.InvalidRequestError as e:
    print(f"\n❌ Error: No se encontró el producto")
    print(f"   Detalles: {e.user_message}")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
