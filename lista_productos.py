import stripe
from builder import StripeClient


def list_products(environment: str = None, limit: int = 100):
    """
    Lista todos los productos de Stripe.
    
    Args:
        environment: 'sandbox' o 'prod'. Si no se especifica, usa el del .env
        limit: Número máximo de productos a mostrar (máximo 100)
    """
    try:
        # Conectar a Stripe
        client = StripeClient(environment)
        
        print(f"\n📦 Listando productos en ambiente: {client.environment.upper()}")
        print("=" * 80)
        
        # Obtener productos
        products = stripe.Product.list(limit=limit, active=True)
        
        if not products.data:
            print("No hay productos disponibles.")
            return
        
        # Mostrar productos
        for idx, product in enumerate(products.data, 1):
            print(f"\n{idx}. {product.name}")
            print(f"   ID: {product.id}")
            print(f"   Descripción: {product.description or 'N/A'}")
            print(f"   Estado: {'Activo' if product.active else 'Inactivo'}")
            print(f"   Creado: {product.created}")
            
            # Obtener precios asociados
            prices = stripe.Price.list(product=product.id, limit=10)
            if prices.data:
                print(f"   Precios:")
                for price in prices.data:
                    currency = price.currency.upper()
                    if price.type == 'recurring':
                        amount = price.unit_amount / 100 if price.unit_amount else 'Variable'
                        interval = price.recurring.interval if price.recurring else 'N/A'
                        print(f"      - ${amount} {currency} (recurrente: {interval})")
                    else:
                        amount = price.unit_amount / 100 if price.unit_amount else 'Variable'
                        print(f"      - ${amount} {currency} (una sola vez)")
        
        print("\n" + "=" * 80)
        print(f"✅ Total de productos: {len(products.data)}\n")
    
    except Exception as e:
        print(f"❌ Error al listar productos: {e}\n")


def main():
    """Función principal."""
    import sys
    
    # Obtener ambiente si se especifica como argumento
    environment = sys.argv[1] if len(sys.argv) > 1 else None
    
    list_products(environment)


if __name__ == '__main__':
    main()
